import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.tools.artifact_tools import (
    audit_workspace_artifact_consumers_payload,
    execute_workspace_foldered_canonical_broader_rollout_commit_payload,
    execute_workspace_foldered_canonical_broader_rollout_rollback_payload,
    execute_workspace_foldered_canonical_broader_rollout_payload,
    execute_workspace_foldered_canonical_legacy_fallback_tightening_payload,
    execute_workspace_foldered_canonical_migration_finalization_payload,
    execute_workspace_foldered_canonical_physical_apply_payload,
    plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload,
    record_workspace_foldered_canonical_broader_rollout_decision_payload,
    plan_workspace_foldered_canonical_broader_rollout_payload,
    plan_workspace_foldered_canonical_legacy_fallback_tightening_payload,
    plan_workspace_foldered_canonical_migration_finalization_payload,
    record_workspace_foldered_canonical_migration_post_apply_validation_result_payload,
    review_workspace_foldered_canonical_broader_rollout_post_audit_payload,
    review_workspace_foldered_canonical_broader_rollout_preflight_payload,
    review_workspace_foldered_canonical_broader_rollout_readiness_payload,
    review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload,
    review_workspace_foldered_canonical_migration_post_finalization_audit_payload,
    review_workspace_foldered_canonical_migration_finalization_readiness_payload,
    review_workspace_foldered_canonical_migration_finalization_preflight_payload,
    review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_payload,
    review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload,
    make_audit_workspace_artifact_consumers_tool,
    make_execute_workspace_foldered_canonical_broader_rollout_commit_tool,
    make_execute_workspace_foldered_canonical_broader_rollout_rollback_tool,
    make_execute_workspace_foldered_canonical_broader_rollout_tool,
    make_execute_workspace_foldered_canonical_legacy_fallback_tightening_tool,
    make_execute_workspace_foldered_canonical_migration_finalization_tool,
    make_execute_workspace_foldered_canonical_physical_apply_tool,
    make_plan_workspace_foldered_canonical_broader_rollout_rollback_decision_tool,
    make_record_workspace_foldered_canonical_broader_rollout_decision_tool,
    make_plan_workspace_foldered_canonical_broader_rollout_tool,
    make_review_workspace_foldered_canonical_broader_rollout_post_audit_tool,
    make_review_workspace_foldered_canonical_broader_rollout_preflight_tool,
    make_review_workspace_foldered_canonical_broader_rollout_rollback_preflight_tool,
    make_plan_workspace_foldered_canonical_migration_finalization_tool,
    make_review_workspace_foldered_canonical_broader_rollout_readiness_tool,
    make_review_workspace_foldered_canonical_migration_post_finalization_audit_tool,
    make_review_workspace_foldered_canonical_migration_finalization_preflight_tool,
    make_plan_workspace_foldered_canonical_migration_pilot_tool,
    make_plan_workspace_foldered_canonical_migration_apply_tool,
    make_plan_workspace_foldered_canonical_migration_approval_tool,
    make_plan_workspace_foldered_canonical_legacy_fallback_tightening_tool,
    make_review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_tool,
    make_review_workspace_foldered_canonical_migration_finalization_readiness_tool,
    make_review_workspace_foldered_canonical_migration_manifest_dry_run_tool,
    make_review_workspace_foldered_canonical_migration_physical_apply_preflight_tool,
    make_review_workspace_foldered_canonical_migration_post_apply_validation_tool,
    make_review_workspace_foldered_canonical_migration_preflight_tool,
    make_record_workspace_foldered_canonical_migration_post_apply_validation_result_tool,
    make_review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_tool,
    make_read_workspace_artifact_tool,
    plan_workspace_foldered_canonical_migration_pilot_payload,
    plan_workspace_foldered_canonical_migration_apply_payload,
    plan_workspace_foldered_canonical_migration_approval_payload,
    review_workspace_foldered_canonical_migration_manifest_dry_run_payload,
    review_workspace_foldered_canonical_migration_physical_apply_preflight_payload,
    review_workspace_foldered_canonical_migration_post_apply_validation_payload,
    review_workspace_foldered_canonical_migration_preflight_payload,
    read_workspace_artifact_payload,
    summarize_workspace_artifact_read,
)
from reverse_deepagent.tools.workspace_migration_readiness import (
    assess_workspace_consumer_readiness_score_payload,
    assess_workspace_migration_readiness_payload,
    make_assess_workspace_consumer_readiness_score_tool,
    make_assess_workspace_migration_readiness_tool,
    make_plan_workspace_dual_write_expansion_tool,
    make_record_workspace_dual_write_expansion_result_tool,
    make_review_workspace_dual_write_expansion_workflow_tool,
    plan_workspace_dual_write_expansion_payload,
    record_workspace_dual_write_expansion_result_payload,
    review_workspace_dual_write_expansion_workflow_payload,
)
from reverse_deepagent.tools.workspace_dual_write_pilot import (
    make_plan_workspace_dual_write_pilot_tool,
    make_record_workspace_dual_write_pilot_result_tool,
    make_review_workspace_dual_write_pilot_workflow_tool,
    plan_workspace_dual_write_pilot_payload,
    record_workspace_dual_write_pilot_result_payload,
    review_workspace_dual_write_pilot_workflow_payload,
)



class WorkspaceArtifactReaderTests(unittest.TestCase):
    def _ready_workspace_dual_write_expansion_plan(self, root: Path, artifact_keys: list[str] | None = None) -> dict:
        readiness_score = {
            "schema_version": "reverse-deepagent.workspace-consumer-readiness-score.v1",
            "status": "ready_for_limited_dual_write_review",
            "summary": {
                "overall_score": 0.75,
                "overall_label": "ready_for_limited_dual_write_review",
            },
            "readiness": {
                "limited_dual_write_expansion_review_allowed": True,
                "foldered_canonical_migration_allowed": False,
            },
            "pilot_evidence": {
                "schema_version": "reverse-deepagent.workspace-dual-write-pilot-result.v1",
                "status": "verified",
                "score": 1.0,
            },
            "blocking_reasons": ["resolver_adoption_incomplete"],
            "warnings": [],
        }
        return plan_workspace_dual_write_expansion_payload(
            default_artifact_root=root,
            readiness_score_json=json.dumps(readiness_score),
            artifact_keys_json=json.dumps(artifact_keys or ["workspace_task_card", "workspace_runtime_context"]),
        )

    def _ready_foldered_canonical_readiness_score(self) -> dict:
        return {
            "schema_version": "reverse-deepagent.workspace-consumer-readiness-score.v1",
            "status": "ready_for_foldered_canonical_review",
            "summary": {
                "overall_score": 0.95,
                "overall_label": "ready_for_foldered_canonical_review",
            },
            "readiness": {
                "limited_dual_write_expansion_review_allowed": True,
                "foldered_canonical_migration_allowed": True,
            },
            "pilot_evidence": {
                "schema_version": "reverse-deepagent.workspace-dual-write-pilot-result.v1",
                "status": "verified",
                "score": 1.0,
            },
            "blocking_reasons": [],
            "warnings": [],
        }

    def _verified_workspace_dual_write_expansion_result(self, plan: dict) -> dict:
        return {
            "schema_version": "reverse-deepagent.workspace-dual-write-expansion-result.v1",
            "status": "verified",
            "summary": {
                "planned_candidate_count": len(plan["candidate_artifacts"]),
                "verified_candidate_count": len(plan["candidate_artifacts"]),
                "out_of_scope_observed_count": 0,
                "high_risk_observed_count": 0,
                "medium_risk_observed_count": 0,
            },
            "candidate_results": [
                {
                    "artifact_key": candidate["artifact_key"],
                    "status": "verified_dual_written",
                    "legacy_path": candidate["legacy_path"],
                    "future_path": candidate["future_path"],
                    "digest_match": True,
                }
                for candidate in plan["candidate_artifacts"]
            ],
            "blocking_reasons": [],
            "warnings": [],
        }

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

    def test_workspace_consumer_readiness_score_blocks_foldered_canonical_until_source_paths_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            delivery_audit = {
                "schema_version": "reverse-deepagent.delivery-artifact-source-audit.v1",
                "artifact_count": 2,
                "source_artifact_ref_count": 1,
                "source_path_count": 1,
                "workspace_resolved_count": 1,
                "external_source_path_count": 1,
                "legacy_source_path_count": 0,
                "future_source_path_count": 0,
                "artifact_root_relative_source_path_count": 0,
                "relative_source_path_count": 0,
            }

            payload = assess_workspace_consumer_readiness_score_payload(
                default_artifact_root=root,
                delivery_source_audit_json=json.dumps(delivery_audit),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-consumer-readiness-score.v1")
            self.assertEqual(payload["status"], "ready_for_limited_dual_write_review")
            self.assertFalse(payload["readiness"]["foldered_canonical_migration_allowed"])
            self.assertTrue(payload["readiness"]["limited_dual_write_expansion_review_allowed"])
            self.assertIn("source_path_usage_observed", payload["blocking_reasons"])
            self.assertIn("external_source_path_usage_observed", payload["blocking_reasons"])
            self.assertIn("dual_write_pilot_result_not_observed", payload["warnings"])
            self.assertEqual(payload["scores"]["source_path_risk"], 0.0)
            self.assertEqual(payload["pilot_evidence"]["status"], "not_observed")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse((root / "workspace" / "workspace-consumer-readiness-score.json").exists())

    def test_workspace_consumer_readiness_score_uses_verified_pilot_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            readiness_report = assess_workspace_migration_readiness_payload(
                default_artifact_root=root,
                delivery_source_audit_json=json.dumps(
                    {
                        "schema_version": "reverse-deepagent.delivery-artifact-source-audit.v1",
                        "artifact_count": 1,
                        "source_artifact_ref_count": 1,
                        "source_path_count": 0,
                        "workspace_resolved_count": 1,
                        "external_source_path_count": 0,
                    }
                ),
            )
            pilot_result = {
                "schema_version": "reverse-deepagent.workspace-dual-write-pilot-result.v1",
                "status": "verified",
                "summary": {
                    "planned_candidate_count": 2,
                    "verified_candidate_count": 2,
                },
                "blocking_reasons": [],
                "warnings": [],
            }

            payload = assess_workspace_consumer_readiness_score_payload(
                default_artifact_root=root,
                readiness_report_json=json.dumps(readiness_report),
                pilot_result_json=json.dumps(pilot_result),
            )

            self.assertEqual(payload["pilot_evidence"]["status"], "verified")
            self.assertEqual(payload["pilot_evidence"]["score"], 1.0)
            self.assertEqual(payload["scores"]["dual_write_pilot_evidence"], 1.0)
            self.assertEqual(payload["scores"]["source_path_risk"], 1.0)
            self.assertEqual(payload["status"], "ready_for_limited_dual_write_review")
            self.assertIn("resolver_adoption_incomplete", payload["blocking_reasons"])
            self.assertNotIn("dual_write_pilot_result_not_observed", payload["warnings"])
            self.assertIn(
                "close_partial_or_candidate_workspace_consumers_before_foldered_canonical_migration",
                payload["recommended_next_actions"],
            )

    def test_workspace_consumer_readiness_score_tool_returns_payload_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            tool = make_assess_workspace_consumer_readiness_score_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "assess_workspace_consumer_readiness_score")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-consumer-readiness-score.v1")
            self.assertEqual(payload["summary"]["mobile_full_runtime_chains_deferred"], True)
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["creates_directories"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_workspace_dual_write_expansion_plan_blocks_without_verified_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_dual_write_expansion_payload(default_artifact_root=root, max_artifacts=2)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-expansion-plan.v1")
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["summary"]["candidate_count"], 2)
            self.assertIn("verified_dual_write_pilot_result_required_before_expansion", payload["blocking_reasons"])
            self.assertTrue(payload["selection_policy"]["requires_workspace_consumer_readiness_score"])
            self.assertTrue(payload["selection_policy"]["requires_verified_dual_write_pilot_result"])
            self.assertFalse(payload["selection_policy"]["actual_dual_write_enabled"])
            for candidate in payload["candidate_artifacts"]:
                self.assertEqual(candidate["risk"]["risk_level"], "low")
                self.assertTrue(candidate["dual_write_plan"]["dual_write_enabled"])
                self.assertTrue(candidate["dual_write_plan"]["canonical_path_remains_authoritative"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["runs_pipeline"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_workspace_dual_write_expansion_plan_uses_verified_score_and_explicit_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            readiness_score = {
                "schema_version": "reverse-deepagent.workspace-consumer-readiness-score.v1",
                "status": "ready_for_limited_dual_write_review",
                "summary": {
                    "overall_score": 0.75,
                    "overall_label": "ready_for_limited_dual_write_review",
                },
                "readiness": {
                    "limited_dual_write_expansion_review_allowed": True,
                    "foldered_canonical_migration_allowed": False,
                },
                "pilot_evidence": {
                    "schema_version": "reverse-deepagent.workspace-dual-write-pilot-result.v1",
                    "status": "verified",
                    "score": 1.0,
                },
                "blocking_reasons": ["resolver_adoption_incomplete"],
                "warnings": [],
            }

            payload = plan_workspace_dual_write_expansion_payload(
                default_artifact_root=root,
                readiness_score_json=json.dumps(readiness_score),
                artifact_keys_json=json.dumps(["workspace_task_card", "workspace_runtime_context"]),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["candidate_count"], 2)
            self.assertEqual(payload["summary"]["pilot_evidence_score"], 1.0)
            self.assertEqual(payload["blocking_reasons"], [])
            self.assertIn("foldered_canonical_migration_still_requires_separate_review", payload["warnings"])
            self.assertEqual(
                [item["artifact_key"] for item in payload["candidate_artifacts"]],
                ["workspace_task_card", "workspace_runtime_context"],
            )
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])

    def test_workspace_dual_write_expansion_tool_returns_payload_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            tool = make_plan_workspace_dual_write_expansion_tool(root)

            payload = tool(max_artifacts=1)

            self.assertEqual(tool.__name__, "plan_workspace_dual_write_expansion")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-expansion-plan.v1")
            self.assertEqual(payload["summary"]["candidate_count"], 1)
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["creates_directories"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_workspace_dual_write_expansion_result_reports_not_run_without_observed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = self._ready_workspace_dual_write_expansion_plan(root)

            payload = record_workspace_dual_write_expansion_result_payload(
                default_artifact_root=root,
                expansion_plan_json=json.dumps(plan),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-expansion-result.v1")
            self.assertEqual(payload["status"], "not_run")
            self.assertIn("workspace_dual_write_plan_not_observed", payload["blocking_reasons"])
            self.assertFalse(payload["result_artifact"]["written"])
            self.assertEqual(payload["summary"]["planned_candidate_count"], 2)
            self.assertEqual(payload["summary"]["verified_candidate_count"], 0)
            self.assertTrue(payload["summary"]["legacy_canonical_path_remains_authoritative"])
            self.assertFalse(payload["summary"]["foldered_canonical_migration_enabled"])
            self.assertTrue(payload["summary"]["mobile_full_runtime_chains_deferred"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertTrue(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["runs_pipeline"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse((root / "workspace" / "workspace-dual-write-expansion-result.json").exists())

    def test_workspace_dual_write_expansion_result_verifies_matching_legacy_and_future_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = self._ready_workspace_dual_write_expansion_plan(root)
            records = []
            for index, candidate in enumerate(plan["candidate_artifacts"], start=1):
                legacy = root / candidate["legacy_path"]
                future = root / candidate["future_path"].lstrip("/")
                legacy.parent.mkdir(parents=True, exist_ok=True)
                future.parent.mkdir(parents=True, exist_ok=True)
                payload_text = json.dumps({"artifact_key": candidate["artifact_key"], "n": index}, sort_keys=True) + "\n"
                legacy.write_text(payload_text, encoding="utf-8")
                future.write_text(payload_text, encoding="utf-8")
                records.append({
                    "artifact_key": candidate["artifact_key"],
                    "canonical_path": candidate["legacy_path"],
                    "future_path": candidate["future_path"],
                    "write_paths": [str(legacy), str(future)],
                    "dual_write_enabled": True,
                    "canonical_path_remains_authoritative": True,
                })
            observed = {
                "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
                "status": "applied",
                "mode": "scoped-opt-in-dual-write",
                "records": records,
            }

            result = record_workspace_dual_write_expansion_result_payload(
                default_artifact_root=root,
                expansion_plan_json=json.dumps(plan),
                workspace_dual_write_plan_json=json.dumps(observed),
            )

            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["summary"]["planned_candidate_count"], 2)
            self.assertEqual(result["summary"]["verified_candidate_count"], 2)
            self.assertEqual(result["summary"]["out_of_scope_observed_count"], 0)
            self.assertEqual(result["summary"]["high_risk_observed_count"], 0)
            self.assertEqual(result["summary"]["digest_mismatch_count"], 0)
            self.assertFalse(result["result_artifact"]["written"])
            self.assertTrue(all(item["status"] == "verified_dual_written" for item in result["candidate_results"]))
            self.assertTrue(all(item["digest_match"] for item in result["candidate_results"]))
            self.assertTrue(result["side_effect_policy"]["read_only"])
            self.assertFalse(result["side_effect_policy"]["artifacts_written"])
            self.assertFalse(result["side_effect_policy"]["runs_pipeline"])
            self.assertFalse(result["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(result["side_effect_policy"]["migrates_paths"])
            self.assertFalse(result["side_effect_policy"]["changes_canonical_paths"])

    def test_workspace_dual_write_expansion_result_can_write_audit_artifact_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            candidate = plan["candidate_artifacts"][0]
            legacy = root / candidate["legacy_path"]
            future = root / candidate["future_path"].lstrip("/")
            legacy.parent.mkdir(parents=True, exist_ok=True)
            future.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text('{"ok": true}\n', encoding="utf-8")
            future.write_text('{"ok": true}\n', encoding="utf-8")
            observed = {
                "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
                "status": "applied",
                "records": [
                    {
                        "artifact_key": candidate["artifact_key"],
                        "canonical_path": candidate["legacy_path"],
                        "future_path": candidate["future_path"],
                        "write_paths": [str(legacy), str(future)],
                        "dual_write_enabled": True,
                        "canonical_path_remains_authoritative": True,
                    }
                ],
            }

            result = record_workspace_dual_write_expansion_result_payload(
                default_artifact_root=root,
                expansion_plan_json=json.dumps(plan),
                workspace_dual_write_plan_json=json.dumps(observed),
                write_result=True,
            )

            result_path = root / "workspace" / "workspace-dual-write-expansion-result.json"
            self.assertEqual(result["status"], "verified")
            self.assertTrue(result["result_artifact"]["written"])
            self.assertEqual(result["result_artifact"]["path"], str(result_path))
            self.assertTrue(result_path.exists())
            written = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], "reverse-deepagent.workspace-dual-write-expansion-result.v1")
            self.assertEqual(written["status"], "verified")
            self.assertFalse(written["side_effect_policy"]["read_only"])
            self.assertTrue(written["side_effect_policy"]["artifacts_written"])
            self.assertFalse(written["side_effect_policy"]["runs_pipeline"])
            self.assertFalse(written["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(written["side_effect_policy"]["migrates_paths"])
            self.assertFalse(written["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse((root / "workspace" / "review" / "workspace-dual-write-expansion-result.json").exists())

    def test_workspace_dual_write_expansion_workflow_returns_review_plan_without_running_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])

            payload = review_workspace_dual_write_expansion_workflow_payload(
                default_artifact_root=root,
                expansion_plan_json=json.dumps(plan),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-expansion-workflow.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["expansion_plan_status"], "ready_for_review")
            self.assertEqual(payload["summary"]["expansion_result_status"], "not_run")
            self.assertEqual(payload["summary"]["candidate_count"], 1)
            self.assertEqual(payload["review_workflow"]["selected_artifact_keys"], ["workspace_task_card"])
            self.assertTrue(payload["review_workflow"]["requires_explicit_pipeline_run"])
            self.assertTrue(payload["review_workflow"]["requires_review_before_expansion"])
            self.assertTrue(payload["review_workflow"]["does_not_run_pipeline"])
            self.assertTrue(payload["review_workflow"]["does_not_enable_dual_write"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertTrue(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["runs_pipeline"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse((root / "workspace" / "workspace-dual-write-expansion-result.json").exists())

    def test_workspace_dual_write_expansion_workflow_verifies_observed_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            candidate = plan["candidate_artifacts"][0]
            legacy = root / candidate["legacy_path"]
            future = root / candidate["future_path"].lstrip("/")
            legacy.parent.mkdir(parents=True, exist_ok=True)
            future.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text('{"task": "demo"}\n', encoding="utf-8")
            future.write_text('{"task": "demo"}\n', encoding="utf-8")
            observed = {
                "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
                "status": "applied",
                "records": [
                    {
                        "artifact_key": candidate["artifact_key"],
                        "canonical_path": candidate["legacy_path"],
                        "future_path": candidate["future_path"],
                        "write_paths": [str(legacy), str(future)],
                        "dual_write_enabled": True,
                    }
                ],
            }

            result = review_workspace_dual_write_expansion_workflow_payload(
                default_artifact_root=root,
                expansion_plan_json=json.dumps(plan),
                workspace_dual_write_plan_json=json.dumps(observed),
            )

            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["summary"]["expansion_result_status"], "verified")
            self.assertEqual(result["expansion_result"]["summary"]["verified_candidate_count"], 1)
            self.assertEqual(result["expansion_result"]["candidate_results"][0]["status"], "verified_dual_written")
            self.assertTrue(result["side_effect_policy"]["read_only"])
            self.assertFalse(result["side_effect_policy"]["artifacts_written"])
            self.assertFalse(result["side_effect_policy"]["runs_pipeline"])

    def test_workspace_dual_write_expansion_tools_return_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            review_tool = make_review_workspace_dual_write_expansion_workflow_tool(root)
            record_tool = make_record_workspace_dual_write_expansion_result_tool(root)

            review_payload = review_tool(expansion_plan_json=json.dumps(plan))
            record_payload = record_tool(expansion_plan_json=json.dumps(plan))

            self.assertEqual(review_tool.__name__, "review_workspace_dual_write_expansion_workflow")
            self.assertEqual(record_tool.__name__, "record_workspace_dual_write_expansion_result")
            self.assertEqual(review_payload["schema_version"], "reverse-deepagent.workspace-dual-write-expansion-workflow.v1")
            self.assertEqual(record_payload["schema_version"], "reverse-deepagent.workspace-dual-write-expansion-result.v1")
            self.assertEqual(review_payload["status"], "ready_for_review")
            self.assertEqual(record_payload["status"], "not_run")
            self.assertTrue(review_payload["side_effect_policy"]["read_only"])
            self.assertTrue(record_payload["side_effect_policy"]["read_only"])
            self.assertFalse(review_payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(record_payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_pilot_blocks_without_verified_expansion_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_foldered_canonical_migration_pilot_payload(
                default_artifact_root=root,
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-pilot-plan.v1")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("workspace_dual_write_expansion_result_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("verified_workspace_dual_write_expansion_result_required", payload["blocking_reasons"])
            self.assertIn("no_foldered_canonical_migration_candidates_selected", payload["blocking_reasons"])
            self.assertTrue(payload["selection_policy"]["requires_verified_expansion_result"])
            self.assertFalse(payload["selection_policy"]["physical_migration_enabled"])
            self.assertFalse(payload["selection_policy"]["actual_canonical_path_change_enabled"])
            self.assertTrue(payload["summary"]["legacy_canonical_path_remains_authoritative"])
            self.assertFalse(payload["summary"]["physical_migration_enabled"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertTrue(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_pilot_uses_verified_expansion_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card", "workspace_runtime_context"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)

            payload = plan_workspace_foldered_canonical_migration_pilot_payload(
                default_artifact_root=root,
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                expansion_result_json=json.dumps(expansion_result),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["candidate_count"], 2)
            self.assertEqual(payload["summary"]["verified_expansion_artifact_count"], 2)
            self.assertEqual(payload["summary"]["expansion_result_status"], "verified")
            self.assertEqual(payload["blocking_reasons"], [])
            self.assertIn("canonical_path_change_requires_separate_reviewed_execution_after_pilot_plan", payload["warnings"])
            self.assertEqual(
                [item["artifact_key"] for item in payload["candidate_artifacts"]],
                ["workspace_task_card", "workspace_runtime_context"],
            )
            for candidate in payload["candidate_artifacts"]:
                self.assertEqual(candidate["risk"]["risk_level"], "low")
                self.assertTrue(candidate["migration_plan"]["plan_only"])
                self.assertTrue(candidate["migration_plan"]["review_required"])
                self.assertTrue(candidate["migration_plan"]["legacy_canonical_path_remains_authoritative"])
                self.assertFalse(candidate["migration_plan"]["physical_migration_enabled"])
                self.assertFalse(candidate["migration_plan"]["canonical_path_change_enabled"])
                self.assertTrue(candidate["future_canonical_path"].startswith("/workspace/"))
                self.assertTrue(candidate["virtual_uri"].startswith("virtual://workspace/"))
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["runs_pipeline"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])

    def test_foldered_canonical_migration_pilot_can_read_expansion_result_artifact_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            result_path = root / "workspace" / "workspace-dual-write-expansion-result.json"
            result_path.parent.mkdir(parents=True)
            result_path.write_text(json.dumps(expansion_result), encoding="utf-8")

            payload = plan_workspace_foldered_canonical_migration_pilot_payload(
                default_artifact_root=root,
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["expansion_result_input"]["source"], "artifact-ref")
            self.assertEqual(payload["expansion_result_input"]["artifact_ref"], "workspace_dual_write_expansion_result")
            self.assertEqual(payload["expansion_result_input"]["read_status"], "found")
            self.assertEqual(payload["candidate_artifacts"][0]["artifact_key"], "workspace_task_card")

    def test_foldered_canonical_migration_pilot_tool_returns_payload_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            tool = make_plan_workspace_foldered_canonical_migration_pilot_tool(root)

            payload = tool(
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                expansion_result_json=json.dumps(expansion_result),
            )

            self.assertEqual(tool.__name__, "plan_workspace_foldered_canonical_migration_pilot")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-pilot-plan.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["creates_directories"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_preflight_blocks_without_ready_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_migration_preflight_payload(default_artifact_root=root)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-preflight.v1")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_migration_pilot_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("foldered_canonical_migration_pilot_plan_not_ready", payload["blocking_reasons"])
            self.assertIn("foldered_canonical_migration_pilot_has_no_candidates", payload["blocking_reasons"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertTrue(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_preflight_verifies_matching_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card", "workspace_runtime_context"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            pilot_plan = plan_workspace_foldered_canonical_migration_pilot_payload(
                default_artifact_root=root,
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                expansion_result_json=json.dumps(expansion_result),
            )
            for candidate in pilot_plan["candidate_artifacts"]:
                legacy = root / candidate["current_canonical_path"]
                future = root / candidate["future_canonical_path"].lstrip("/")
                legacy.parent.mkdir(parents=True, exist_ok=True)
                future.parent.mkdir(parents=True, exist_ok=True)
                payload_bytes = json.dumps({"artifact_key": candidate["artifact_key"], "ok": True}, sort_keys=True).encode("utf-8")
                legacy.write_bytes(payload_bytes)
                future.write_bytes(payload_bytes)

            payload = review_workspace_foldered_canonical_migration_preflight_payload(
                default_artifact_root=root,
                migration_pilot_plan_json=json.dumps(pilot_plan),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["ready_candidate_count"], payload["summary"]["candidate_count"])
            self.assertEqual(payload["summary"]["candidate_count"], 2)
            self.assertTrue(payload["execution_gate"]["ready_for_reviewed_execution"])
            self.assertFalse(payload["execution_gate"]["allows_automatic_execution"])
            self.assertFalse(payload["execution_gate"]["allows_manifest_mutation"])
            self.assertFalse(payload["execution_gate"]["allows_canonical_path_change_in_this_tool"])
            self.assertTrue(payload["rollback_plan"]["plan_only"])
            self.assertFalse(payload["rollback_plan"]["automatic_rollback"])
            self.assertTrue(all(item["status"] == "ready_for_reviewed_execution" for item in payload["candidate_results"]))
            self.assertTrue(all(item["digest_match"] for item in payload["candidate_results"]))
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_foldered_canonical_migration_preflight_blocks_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            pilot_plan = plan_workspace_foldered_canonical_migration_pilot_payload(
                default_artifact_root=root,
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                expansion_result_json=json.dumps(expansion_result),
            )
            candidate = pilot_plan["candidate_artifacts"][0]
            legacy = root / candidate["current_canonical_path"]
            future = root / candidate["future_canonical_path"].lstrip("/")
            legacy.parent.mkdir(parents=True, exist_ok=True)
            future.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text('{"ok": true}\n', encoding="utf-8")
            future.write_text('{"ok": false}\n', encoding="utf-8")

            payload = review_workspace_foldered_canonical_migration_preflight_payload(
                default_artifact_root=root,
                migration_pilot_plan_json=json.dumps(pilot_plan),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("candidate_digest_mismatch", payload["blocking_reasons"])
            self.assertEqual(payload["summary"]["digest_mismatch_count"], 1)
            self.assertEqual(payload["candidate_results"][0]["status"], "digest_mismatch")
            self.assertFalse(payload["execution_gate"]["ready_for_reviewed_execution"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_preflight_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            pilot_plan = plan_workspace_foldered_canonical_migration_pilot_payload(
                default_artifact_root=root,
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                expansion_result_json=json.dumps(expansion_result),
            )
            candidate = pilot_plan["candidate_artifacts"][0]
            legacy = root / candidate["current_canonical_path"]
            future = root / candidate["future_canonical_path"].lstrip("/")
            legacy.parent.mkdir(parents=True, exist_ok=True)
            future.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text('{"ok": true}\n', encoding="utf-8")
            future.write_text('{"ok": true}\n', encoding="utf-8")
            tool = make_review_workspace_foldered_canonical_migration_preflight_tool(root)

            payload = tool(migration_pilot_plan_json=json.dumps(pilot_plan))

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_migration_preflight")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-preflight.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def _ready_foldered_canonical_migration_preflight(self, root: Path, artifact_keys: list[str] | None = None) -> dict:
        expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, artifact_keys or ["workspace_task_card"])
        expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
        pilot_plan = plan_workspace_foldered_canonical_migration_pilot_payload(
            default_artifact_root=root,
            readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
            expansion_result_json=json.dumps(expansion_result),
        )
        for candidate in pilot_plan["candidate_artifacts"]:
            legacy = root / candidate["current_canonical_path"]
            future = root / candidate["future_canonical_path"].lstrip("/")
            legacy.parent.mkdir(parents=True, exist_ok=True)
            future.parent.mkdir(parents=True, exist_ok=True)
            payload_bytes = json.dumps({"artifact_key": candidate["artifact_key"], "ok": True}, sort_keys=True).encode("utf-8")
            legacy.write_bytes(payload_bytes)
            future.write_bytes(payload_bytes)
        return review_workspace_foldered_canonical_migration_preflight_payload(
            default_artifact_root=root,
            migration_pilot_plan_json=json.dumps(pilot_plan),
        )

    def _backend_manifest_for_apply_plan(self, apply_plan: dict) -> dict:
        steps = apply_plan.get("apply_plan", {}).get("planned_steps", [])
        return {
            "schema_version": "reverse-deepagent.backend-artifact-manifest.v1",
            "producer_backend_id": "mock",
            "producer_transport": "in-process",
            "target_platforms": ["web"],
            "entries": [
                {
                    "artifact_key": step["artifact_key"],
                    "path": step["current_canonical_path"],
                    "category": "workspace",
                    "kind": "json",
                    "metadata": {
                        "workspace_alias": {
                            "future_path": step["future_canonical_path"],
                            "virtual_uri": step["virtual_uri"],
                        }
                    },
                }
                for step in steps
            ],
        }

    def _post_apply_backend_manifest_for_apply_plan(self, apply_plan: dict) -> dict:
        manifest = self._backend_manifest_for_apply_plan(apply_plan)
        for entry, step in zip(manifest["entries"], apply_plan.get("apply_plan", {}).get("planned_steps", [])):
            entry["path"] = step["future_canonical_path"]
            entry["metadata"]["workspace_alias"]["canonical_path_remains_authoritative"] = False
            entry["metadata"]["workspace_alias"]["legacy_fallback_path"] = step["current_canonical_path"]
        return manifest

    def _approval_ledger_for_physical_apply(self, dry_run: dict, *, digest_override: str | None = None) -> dict:
        digest = digest_override or dry_run["digest_guard"]["current_apply_plan_digest"]
        rollback = dry_run.get("rollback_checkpoint", {})
        return {
            "version": "2026-06-01.review-approval-ledger-v1",
            "entry_count": 1,
            "entries": [
                {
                    "approval_id": "approval-foldered-physical-apply",
                    "subject_id": f"workspace-foldered-canonical-physical-apply:{dry_run['digest_guard']['current_apply_plan_digest']}",
                    "action": "foldered_canonical_physical_apply",
                    "decision": "approved",
                    "status": "written",
                    "reviewer": "reviewer-a",
                    "subject_digest_sha256": digest,
                    "metadata": {
                        "transaction_id": rollback.get("transaction_id") or "tx-foldered-apply",
                        "idempotency_key": rollback.get("idempotency_key") or "idem-foldered-apply",
                    },
                }
            ],
        }

    def _approval_ledger_for_legacy_fallback_tightening(self, plan: dict, *, digest_override: str | None = None) -> dict:
        digest = digest_override or plan["digest_guard"]["legacy_fallback_tightening_plan_digest"]
        return {
            "version": "2026-06-01.review-approval-ledger-v1",
            "entry_count": 1,
            "entries": [
                {
                    "approval_id": "approval-foldered-legacy-fallback-tightening",
                    "subject_id": plan["approval_requirements"]["subject_id"],
                    "action": "foldered_canonical_legacy_fallback_tightening",
                    "decision": "approved",
                    "status": "written",
                    "reviewer": "reviewer-a",
                    "subject_digest_sha256": digest,
                    "metadata": {
                        "idempotency_key": "idem-legacy-fallback-tightening",
                    },
                }
            ],
        }

    def _approval_ledger_for_finalization(self, plan: dict, *, digest_override: str | None = None) -> dict:
        digest = digest_override or plan["digest_guard"]["foldered_canonical_finalization_plan_digest"]
        return {
            "version": "2026-06-01.review-approval-ledger-v1",
            "entry_count": 1,
            "entries": [
                {
                    "approval_id": "approval-foldered-finalization",
                    "subject_id": plan["approval_requirements"]["subject_id"],
                    "action": "foldered_canonical_migration_finalization",
                    "decision": "approved",
                    "status": "written",
                    "reviewer": "reviewer-a",
                    "subject_digest_sha256": digest,
                    "metadata": {
                        "idempotency_key": "idem-foldered-finalization",
                    },
                }
            ],
        }

    def _approval_ledger_for_broader_rollout(self, plan: dict, *, digest_override: str | None = None) -> dict:
        digest = digest_override or plan["digest_guard"]["broader_rollout_plan_digest"]
        return {
            "version": "2026-06-01.review-approval-ledger-v1",
            "entry_count": 1,
            "entries": [
                {
                    "approval_id": "approval-foldered-broader-rollout",
                    "subject_id": plan["approval_requirements"]["subject_id"],
                    "action": "foldered_canonical_broader_rollout",
                    "decision": "approved",
                    "status": "written",
                    "reviewer": "reviewer-a",
                    "subject_digest_sha256": digest,
                    "metadata": {
                        "idempotency_key": "idem-foldered-broader-rollout",
                    },
                }
            ],
        }

    def _ready_physical_apply_evidence(self, root: Path, artifact_keys: list[str] | None = None) -> tuple[dict, dict, dict, dict]:
        preflight = self._ready_foldered_canonical_migration_preflight(root, artifact_keys or ["workspace_task_card"])
        apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
            default_artifact_root=root,
            migration_preflight_json=json.dumps(preflight),
        )
        approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
            default_artifact_root=root,
            migration_apply_plan_json=json.dumps(apply_plan),
            transaction_id="tx-foldered-physical",
            idempotency_key="idem-foldered-physical",
        )
        dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
            default_artifact_root=root,
            migration_approval_plan_json=json.dumps(approval_plan),
            migration_apply_plan_json=json.dumps(apply_plan),
            backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
        )
        physical_preflight = review_workspace_foldered_canonical_migration_physical_apply_preflight_payload(
            default_artifact_root=root,
            migration_manifest_dry_run_json=json.dumps(dry_run),
            migration_apply_plan_json=json.dumps(apply_plan),
            review_approval_ledger_json=json.dumps(self._approval_ledger_for_physical_apply(dry_run)),
        )
        backend_manifest = self._backend_manifest_for_apply_plan(apply_plan)
        return apply_plan, dry_run, physical_preflight, backend_manifest

    def _write_physical_apply_evidence_artifacts(
        self,
        root: Path,
        *,
        apply_plan: dict,
        dry_run: dict,
        physical_preflight: dict,
        backend_manifest: dict,
    ) -> None:
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "workspace-foldered-canonical-migration-apply-plan.json").write_text(
            json.dumps(apply_plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (workspace / "workspace-foldered-canonical-migration-manifest-dry-run.json").write_text(
            json.dumps(dry_run, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (workspace / "workspace-foldered-canonical-migration-physical-apply-preflight.json").write_text(
            json.dumps(physical_preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (workspace / "backend-artifact-manifest.json").write_text(
            json.dumps(backend_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _ready_legacy_fallback_tightening_plan(self, root: Path, artifact_keys: list[str] | None = None) -> tuple[dict, dict]:
        apply_plan, dry_run, physical_preflight, backend_manifest = self._ready_physical_apply_evidence(
            root,
            artifact_keys or ["workspace_task_card"],
        )
        self._write_physical_apply_evidence_artifacts(
            root,
            apply_plan=apply_plan,
            dry_run=dry_run,
            physical_preflight=physical_preflight,
            backend_manifest=backend_manifest,
        )
        execute_workspace_foldered_canonical_physical_apply_payload(
            default_artifact_root=root,
            mode="apply",
            approve_physical_apply=True,
        )
        promoted_manifest = json.loads((root / "workspace" / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
        validation = review_workspace_foldered_canonical_migration_post_apply_validation_payload(
            default_artifact_root=root,
            migration_manifest_dry_run_json=json.dumps(dry_run),
            migration_apply_plan_json=json.dumps(apply_plan),
            post_apply_backend_manifest_json=json.dumps(promoted_manifest),
        )
        validation_result = record_workspace_foldered_canonical_migration_post_apply_validation_result_payload(
            default_artifact_root=root,
            post_apply_validation_json=json.dumps(validation),
        )
        readiness = review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_payload(
            default_artifact_root=root,
            post_apply_validation_result_json=json.dumps(validation_result),
            readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
        )
        plan = plan_workspace_foldered_canonical_legacy_fallback_tightening_payload(
            default_artifact_root=root,
            legacy_fallback_tightening_readiness_json=json.dumps(readiness),
            backend_manifest_json=json.dumps(promoted_manifest),
        )
        return plan, promoted_manifest

    def _ready_finalization_plan(self, root: Path, artifact_keys: list[str] | None = None) -> tuple[dict, dict]:
        tightening_plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(
            root,
            artifact_keys or ["workspace_task_card"],
        )
        tightening_preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
            default_artifact_root=root,
            legacy_fallback_tightening_plan_json=json.dumps(tightening_plan),
            backend_manifest_json=json.dumps(promoted_manifest),
            review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(tightening_plan)),
        )
        tightening_result = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
            default_artifact_root=root,
            mode="apply",
            approve_legacy_fallback_tightening=True,
            legacy_fallback_tightening_preflight_json=json.dumps(tightening_preflight),
            legacy_fallback_tightening_plan_json=json.dumps(tightening_plan),
        )
        tightened_manifest = json.loads((root / "workspace" / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
        readiness = review_workspace_foldered_canonical_migration_finalization_readiness_payload(
            default_artifact_root=root,
            legacy_fallback_tightening_result_json=json.dumps(tightening_result),
            backend_manifest_json=json.dumps(tightened_manifest),
        )
        plan = plan_workspace_foldered_canonical_migration_finalization_payload(
            default_artifact_root=root,
            finalization_readiness_json=json.dumps(readiness),
            backend_manifest_json=json.dumps(tightened_manifest),
        )
        return plan, tightened_manifest

    def _applied_finalization_evidence(self, root: Path, artifact_keys: list[str] | None = None) -> tuple[dict, dict, dict]:
        plan, tightened_manifest = self._ready_finalization_plan(root, artifact_keys or ["workspace_task_card"])
        preflight = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
            default_artifact_root=root,
            finalization_plan_json=json.dumps(plan),
            backend_manifest_json=json.dumps(tightened_manifest),
            review_approval_ledger_json=json.dumps(self._approval_ledger_for_finalization(plan)),
        )
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "workspace-foldered-canonical-migration-finalization-plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (workspace / "workspace-foldered-canonical-migration-finalization-preflight.json").write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (workspace / "backend-artifact-manifest.json").write_text(
            json.dumps(tightened_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = execute_workspace_foldered_canonical_migration_finalization_payload(
            default_artifact_root=root,
            mode="apply",
            approve_finalization=True,
        )
        journal = json.loads((workspace / "workspace-foldered-canonical-migration-finalization-journal.json").read_text(encoding="utf-8"))
        manifest = json.loads((workspace / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
        return result, journal, manifest

    def _ready_broader_rollout_plan(self, root: Path, artifact_keys: list[str] | None = None) -> tuple[dict, dict]:
        result, journal, manifest = self._applied_finalization_evidence(root, artifact_keys or ["workspace_task_card"])
        audit = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
            default_artifact_root=root,
            finalization_result_json=json.dumps(result),
            finalization_journal_json=json.dumps(journal),
            backend_manifest_json=json.dumps(manifest),
        )
        expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, artifact_keys or ["workspace_task_card"])
        expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
        readiness = review_workspace_foldered_canonical_broader_rollout_readiness_payload(
            default_artifact_root=root,
            post_finalization_audit_json=json.dumps(audit),
            readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
            delivery_source_audit_json=json.dumps(
                {
                    "schema_version": "reverse-deepagent.delivery-source-audit.v1",
                    "artifact_count": len(artifact_keys or ["workspace_task_card"]),
                    "source_artifact_ref_count": len(artifact_keys or ["workspace_task_card"]),
                    "source_path_count": 0,
                    "workspace_resolved_count": len(artifact_keys or ["workspace_task_card"]),
                    "external_source_path_count": 0,
                }
            ),
            expansion_result_json=json.dumps(expansion_result),
            backend_manifest_json=json.dumps(manifest),
        )
        plan = plan_workspace_foldered_canonical_broader_rollout_payload(
            default_artifact_root=root,
            broader_rollout_readiness_json=json.dumps(readiness),
            backend_manifest_json=json.dumps(manifest),
        )
        return plan, manifest

    def _ready_broader_rollout_preflight(self, root: Path, artifact_keys: list[str] | None = None) -> tuple[dict, dict, dict]:
        plan, manifest = self._ready_broader_rollout_plan(root, artifact_keys or ["workspace_task_card"])
        preflight = review_workspace_foldered_canonical_broader_rollout_preflight_payload(
            default_artifact_root=root,
            broader_rollout_plan_json=json.dumps(plan),
            backend_manifest_json=json.dumps(manifest),
            review_approval_ledger_json=json.dumps(self._approval_ledger_for_broader_rollout(plan)),
        )
        return preflight, plan, manifest

    def _applied_broader_rollout_evidence(self, root: Path, artifact_keys: list[str] | None = None) -> tuple[dict, dict, dict]:
        preflight, plan, manifest = self._ready_broader_rollout_preflight(root, artifact_keys or ["workspace_task_card"])
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "workspace-foldered-canonical-broader-rollout-plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (workspace / "workspace-foldered-canonical-broader-rollout-preflight.json").write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (workspace / "backend-artifact-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = execute_workspace_foldered_canonical_broader_rollout_payload(
            default_artifact_root=root,
            mode="apply",
            approve_broader_rollout=True,
        )
        journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-journal.json").read_text(encoding="utf-8"))
        mutated_manifest = json.loads((workspace / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
        return result, journal, mutated_manifest

    def _verified_broader_rollout_post_audit_evidence(
        self,
        root: Path,
        artifact_keys: list[str] | None = None,
    ) -> tuple[dict, dict]:
        result, journal, manifest = self._applied_broader_rollout_evidence(root, artifact_keys or ["workspace_task_card"])
        post_audit = review_workspace_foldered_canonical_broader_rollout_post_audit_payload(
            default_artifact_root=root,
            broader_rollout_result_json=json.dumps(result),
            broader_rollout_journal_json=json.dumps(journal),
            backend_manifest_json=json.dumps(manifest),
        )
        return post_audit, manifest

    def test_foldered_canonical_migration_apply_plan_blocks_without_ready_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_foldered_canonical_migration_apply_payload(default_artifact_root=root)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-apply-plan.v1")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_migration_preflight_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("foldered_canonical_migration_preflight_not_ready", payload["blocking_reasons"])
            self.assertIn("foldered_canonical_apply_has_no_candidates", payload["blocking_reasons"])
            self.assertFalse(payload["execution_gate"]["ready_for_apply_review"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_apply_plan_uses_ready_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card", "workspace_runtime_context"])

            payload = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["candidate_count"], 2)
            self.assertEqual(payload["summary"]["planned_apply_step_count"], 2)
            self.assertTrue(payload["apply_plan"]["plan_only"])
            self.assertTrue(payload["apply_plan"]["requires_explicit_review_approval"])
            self.assertTrue(payload["apply_plan"]["requires_separate_apply_executor"])
            self.assertFalse(payload["apply_plan"]["apply_executor_invoked"])
            self.assertTrue(payload["manifest_mutation_guard"]["required_before_apply"])
            self.assertFalse(payload["manifest_mutation_guard"]["mutates_manifest_in_this_tool"])
            self.assertEqual(len(payload["manifest_mutation_guard"]["required_manifest_changes_preview"]), 2)
            self.assertTrue(payload["rollback_requirements"]["required_before_apply"])
            self.assertFalse(payload["rollback_requirements"]["automatic_rollback"])
            self.assertTrue(payload["compatibility_guard"]["preserve_legacy_read_fallback_until_after_apply_validation"])
            self.assertTrue(payload["execution_gate"]["ready_for_apply_review"])
            self.assertFalse(payload["execution_gate"]["allows_automatic_execution"])
            self.assertFalse(payload["execution_gate"]["allows_manifest_mutation_in_this_tool"])
            self.assertFalse(payload["execution_gate"]["allows_canonical_path_change_in_this_tool"])
            self.assertTrue(all(step["execute_in_this_tool"] is False for step in payload["apply_plan"]["planned_steps"]))
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["creates_directories"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_foldered_canonical_migration_apply_plan_blocks_unready_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            preflight["status"] = "blocked"
            preflight["execution_gate"]["ready_for_reviewed_execution"] = False
            preflight["blocking_reasons"] = ["candidate_digest_mismatch"]

            payload = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_migration_preflight_not_ready", payload["blocking_reasons"])
            self.assertIn("preflight_execution_gate_not_ready", payload["blocking_reasons"])
            self.assertIn("preflight:candidate_digest_mismatch", payload["blocking_reasons"])
            self.assertEqual(payload["summary"]["planned_apply_step_count"], 0)
            self.assertFalse(payload["execution_gate"]["ready_for_apply_review"])

    def test_foldered_canonical_migration_apply_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            tool = make_plan_workspace_foldered_canonical_migration_apply_tool(root)

            payload = tool(migration_preflight_json=json.dumps(preflight))

            self.assertEqual(tool.__name__, "plan_workspace_foldered_canonical_migration_apply")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-apply-plan.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_approval_plan_blocks_without_ready_apply_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_foldered_canonical_migration_approval_payload(default_artifact_root=root)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-approval-plan.v1")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_migration_apply_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("foldered_canonical_migration_apply_plan_not_ready", payload["blocking_reasons"])
            self.assertIn("apply_plan_has_no_planned_steps", payload["blocking_reasons"])
            self.assertFalse(payload["execution_gate"]["ready_for_approval_review"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_approval_plan_uses_ready_apply_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card", "workspace_runtime_context"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )

            payload = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
                reviewer="reviewer-a",
                review_ticket="ticket-1",
                transaction_id="tx-foldered-1",
                idempotency_key="idem-foldered-1",
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_apply_step_count"], 2)
            self.assertEqual(payload["summary"]["apply_plan_status"], "ready_for_review")
            self.assertTrue(payload["summary"]["requires_review_approval"])
            self.assertTrue(payload["summary"]["requires_transaction_journal"])
            self.assertFalse(payload["summary"]["approval_recorded"])
            self.assertFalse(payload["summary"]["transaction_journal_written"])
            self.assertEqual(payload["approval_requirements"]["reviewer"], "reviewer-a")
            self.assertEqual(payload["approval_requirements"]["review_ticket"], "ticket-1")
            self.assertFalse(payload["approval_requirements"]["records_approval_in_this_tool"])
            self.assertEqual(payload["transaction_journal_plan"]["transaction_id"], "tx-foldered-1")
            self.assertEqual(payload["transaction_journal_plan"]["idempotency_key"], "idem-foldered-1")
            self.assertFalse(payload["transaction_journal_plan"]["writes_journal_in_this_tool"])
            self.assertTrue(payload["idempotency_guard"]["duplicate_apply_guard_required"])
            self.assertFalse(payload["idempotency_guard"]["checks_existing_journal_in_this_tool"])
            self.assertTrue(payload["staleness_guard"]["requires_digest_revalidation_by_apply_executor"])
            self.assertFalse(payload["staleness_guard"]["checks_files_in_this_tool"])
            self.assertFalse(payload["manifest_dry_run_requirements"]["runs_dry_run_in_this_tool"])
            self.assertTrue(payload["manifest_dry_run_requirements"]["manifest_mutation_guard"]["required_before_apply"])
            self.assertEqual(payload["manifest_dry_run_requirements"]["manifest_mutation_guard"]["preview_change_count"], 2)
            self.assertFalse(payload["rollback_checkpoint_requirements"]["writes_checkpoint_in_this_tool"])
            self.assertTrue(payload["rollback_checkpoint_requirements"]["rollback_requirements"]["required_before_apply"])
            self.assertFalse(payload["post_apply_validation_requirements"]["runs_validation_in_this_tool"])
            self.assertTrue(payload["compatibility_window"]["preserve_legacy_read_fallback"])
            self.assertTrue(payload["compatibility_window"]["canonical_switch_not_performed_by_this_tool"])
            self.assertTrue(payload["execution_gate"]["ready_for_approval_review"])
            self.assertFalse(payload["execution_gate"]["allows_automatic_execution"])
            self.assertFalse(payload["execution_gate"]["allows_journal_write_in_this_tool"])
            self.assertFalse(payload["execution_gate"]["allows_manifest_mutation_in_this_tool"])
            self.assertFalse(payload["execution_gate"]["allows_canonical_path_change_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_migration_approval_plan_blocks_unready_apply_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            apply_plan["status"] = "blocked"
            apply_plan["execution_gate"]["ready_for_apply_review"] = False
            apply_plan["blocking_reasons"] = ["not_all_preflight_candidates_ready"]

            payload = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_migration_apply_plan_not_ready", payload["blocking_reasons"])
            self.assertIn("apply_review_gate_not_ready", payload["blocking_reasons"])
            self.assertIn("apply_plan:not_all_preflight_candidates_ready", payload["blocking_reasons"])
            self.assertEqual(payload["summary"]["planned_apply_step_count"], 0)
            self.assertFalse(payload["execution_gate"]["ready_for_approval_review"])

    def test_foldered_canonical_migration_approval_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            tool = make_plan_workspace_foldered_canonical_migration_approval_tool(root)

            payload = tool(migration_apply_plan_json=json.dumps(apply_plan))

            self.assertEqual(tool.__name__, "plan_workspace_foldered_canonical_migration_approval")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-approval-plan.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_manifest_dry_run_blocks_without_ready_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(default_artifact_root=root)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-manifest-dry-run.v1")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_migration_approval_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("foldered_canonical_migration_apply_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["execution_gate"]["ready_for_manifest_dry_run_review"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_manifest_dry_run_uses_ready_approval_apply_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card", "workspace_runtime_context"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
                transaction_id="tx-foldered-2",
                idempotency_key="idem-foldered-2",
            )
            backend_manifest = self._backend_manifest_for_apply_plan(apply_plan)

            payload = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(backend_manifest),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_manifest_change_count"], 2)
            self.assertEqual(payload["summary"]["planned_apply_step_count"], 2)
            self.assertFalse(payload["summary"]["manifest_dry_run_written"])
            self.assertFalse(payload["summary"]["rollback_checkpoint_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertTrue(payload["digest_guard"]["digest_match"])
            self.assertTrue(payload["manifest_dry_run"]["plan_only"])
            self.assertFalse(payload["manifest_dry_run"]["writes_artifact_in_this_tool"])
            self.assertFalse(payload["manifest_dry_run"]["mutates_manifest_in_this_tool"])
            self.assertEqual(payload["manifest_dry_run"]["source_backend_manifest_entry_count"], 2)
            self.assertEqual(len(payload["manifest_dry_run"]["planned_changes"]), 2)
            self.assertTrue(all(change["status"] == "ready_for_manifest_dry_run_review" for change in payload["manifest_dry_run"]["planned_changes"]))
            self.assertTrue(payload["rollback_checkpoint"]["required_before_apply"])
            self.assertFalse(payload["rollback_checkpoint"]["writes_checkpoint_in_this_tool"])
            self.assertEqual(payload["rollback_checkpoint"]["transaction_id"], "tx-foldered-2")
            self.assertEqual(payload["rollback_checkpoint"]["idempotency_key"], "idem-foldered-2")
            self.assertTrue(payload["execution_gate"]["ready_for_manifest_dry_run_review"])
            self.assertFalse(payload["execution_gate"]["allows_automatic_execution"])
            self.assertFalse(payload["execution_gate"]["allows_manifest_mutation_in_this_tool"])
            self.assertFalse(payload["execution_gate"]["allows_rollback_checkpoint_write_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_foldered_canonical_manifest_dry_run_blocks_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            apply_plan["apply_plan"]["planned_steps"][0]["future_canonical_path"] = "/workspace/recon/changed-task-card.json"
            backend_manifest = self._backend_manifest_for_apply_plan(apply_plan)

            payload = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(backend_manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("approval_apply_plan_digest_mismatch", payload["blocking_reasons"])
            self.assertFalse(payload["digest_guard"]["digest_match"])
            self.assertFalse(payload["execution_gate"]["ready_for_manifest_dry_run_review"])

    def test_foldered_canonical_manifest_dry_run_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            backend_manifest = self._backend_manifest_for_apply_plan(apply_plan)
            tool = make_review_workspace_foldered_canonical_migration_manifest_dry_run_tool(root)

            payload = tool(
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(backend_manifest),
            )

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_migration_manifest_dry_run")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-manifest-dry-run.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_post_apply_validation_blocks_without_ready_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_migration_post_apply_validation_payload(default_artifact_root=root)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation.v1")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_migration_manifest_dry_run_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("foldered_canonical_migration_apply_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("post_apply_backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["execution_gate"]["ready_for_post_apply_validation_review"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_post_apply_validation_uses_promoted_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card", "workspace_runtime_context"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )
            post_apply_manifest = self._post_apply_backend_manifest_for_apply_plan(apply_plan)

            payload = review_workspace_foldered_canonical_migration_post_apply_validation_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                post_apply_backend_manifest_json=json.dumps(post_apply_manifest),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_manifest_change_count"], 2)
            self.assertEqual(payload["summary"]["validated_manifest_change_count"], 2)
            self.assertFalse(payload["summary"]["post_apply_validation_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated_by_this_tool"])
            self.assertFalse(payload["summary"]["canonical_path_changed_by_this_tool"])
            self.assertTrue(payload["summary"]["observed_canonical_path_promotion_validated"])
            self.assertFalse(payload["summary"]["legacy_fallback_tightening_allowed"])
            self.assertTrue(payload["digest_guard"]["digest_match"])
            self.assertEqual(len(payload["post_apply_validation"]["validation_results"]), 2)
            self.assertTrue(
                all(
                    result["status"] == "ready_for_post_apply_validation_review"
                    for result in payload["post_apply_validation"]["validation_results"]
                )
            )
            self.assertTrue(payload["compatibility_validation"]["all_promotions_observed"])
            self.assertTrue(payload["compatibility_validation"]["preserve_legacy_read_fallback"])
            self.assertFalse(payload["compatibility_validation"]["legacy_fallback_tightening_allowed_by_this_tool"])
            self.assertTrue(payload["execution_gate"]["ready_for_post_apply_validation_review"])
            self.assertFalse(payload["execution_gate"]["allows_automatic_execution"])
            self.assertFalse(payload["execution_gate"]["allows_manifest_mutation_in_this_tool"])
            self.assertFalse(payload["execution_gate"]["allows_canonical_path_change_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_foldered_canonical_post_apply_validation_blocks_unpromoted_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )

            payload = review_workspace_foldered_canonical_migration_post_apply_validation_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                post_apply_backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn(
                "post_apply_validation:workspace_task_card:blocked_canonical_path_still_legacy",
                payload["blocking_reasons"],
            )
            self.assertFalse(payload["execution_gate"]["ready_for_post_apply_validation_review"])
            self.assertFalse(payload["compatibility_validation"]["all_promotions_observed"])

    def test_foldered_canonical_post_apply_validation_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )
            tool = make_review_workspace_foldered_canonical_migration_post_apply_validation_tool(root)

            payload = tool(
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                post_apply_backend_manifest_json=json.dumps(self._post_apply_backend_manifest_for_apply_plan(apply_plan)),
            )

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_migration_post_apply_validation")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_record_foldered_canonical_post_apply_validation_result_blocks_without_ready_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = record_workspace_foldered_canonical_migration_post_apply_validation_result_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation-result.v1",
            )
            self.assertEqual(payload["status"], "not_ready")
            self.assertIn("post_apply_validation_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-post-apply-validation-result.json").exists())

    def test_record_foldered_canonical_post_apply_validation_result_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )
            validation = review_workspace_foldered_canonical_migration_post_apply_validation_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                post_apply_backend_manifest_json=json.dumps(self._post_apply_backend_manifest_for_apply_plan(apply_plan)),
            )

            payload = record_workspace_foldered_canonical_migration_post_apply_validation_result_payload(
                default_artifact_root=root,
                post_apply_validation_json=json.dumps(validation),
            )

            self.assertEqual(payload["status"], "verified")
            self.assertEqual(payload["summary"]["validation_result_count"], 1)
            self.assertEqual(payload["summary"]["ready_validation_result_count"], 1)
            self.assertTrue(payload["summary"]["observed_canonical_path_promotion_validated"])
            self.assertTrue(payload["summary"]["all_promotions_observed"])
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["summary"]["legacy_fallback_tightened"])
            self.assertFalse(payload["summary"]["foldered_canonical_finalized"])
            self.assertFalse(payload["legacy_fallback_review_gate"]["legacy_fallback_tightening_allowed_by_this_tool"])
            self.assertFalse(payload["finalization_gate"]["foldered_canonical_finalization_allowed_by_this_tool"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-post-apply-validation-result.json").exists())

    def test_record_foldered_canonical_post_apply_validation_result_can_write_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card", "workspace_runtime_context"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )
            validation = review_workspace_foldered_canonical_migration_post_apply_validation_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                post_apply_backend_manifest_json=json.dumps(self._post_apply_backend_manifest_for_apply_plan(apply_plan)),
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-migration-post-apply-validation.json").write_text(
                json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            payload = record_workspace_foldered_canonical_migration_post_apply_validation_result_payload(
                default_artifact_root=root,
                write_result=True,
            )

            result_path = workspace / "workspace-foldered-canonical-migration-post-apply-validation-result.json"
            self.assertEqual(payload["status"], "verified")
            self.assertTrue(payload["summary"]["result_artifact_written"])
            self.assertTrue(payload["result_artifact"]["written"])
            self.assertTrue(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            self.assertTrue(result_path.exists())
            written = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], payload["schema_version"])
            self.assertEqual(written["status"], "verified")
            self.assertEqual(written["summary"]["ready_validation_result_count"], 2)
            self.assertIn("review_legacy_fallback_tightening_readiness_before_any_fallback_change", written["recommended_next_actions"])

    def test_record_foldered_canonical_post_apply_validation_result_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )
            validation = review_workspace_foldered_canonical_migration_post_apply_validation_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                post_apply_backend_manifest_json=json.dumps(self._post_apply_backend_manifest_for_apply_plan(apply_plan)),
            )
            tool = make_record_workspace_foldered_canonical_migration_post_apply_validation_result_tool(root)

            payload = tool(post_apply_validation_json=json.dumps(validation))

            self.assertEqual(tool.__name__, "record_workspace_foldered_canonical_migration_post_apply_validation_result")
            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation-result.v1",
            )
            self.assertEqual(payload["status"], "verified")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])

    def test_legacy_fallback_tightening_readiness_blocks_without_validation_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-readiness.v1",
            )
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("post_apply_validation_result_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("workspace_consumer_readiness_score_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["tightening_plan_gate"]["ready_for_legacy_fallback_tightening_plan_review"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_legacy_fallback_tightening_readiness_uses_verified_result_and_readiness_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            validation_result = {
                "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation-result.v1",
                "status": "verified",
                "summary": {
                    "validation_result_count": 2,
                    "ready_validation_result_count": 2,
                    "all_promotions_observed": True,
                    "observed_canonical_path_promotion_validated": True,
                    "result_artifact_written": True,
                    "legacy_fallback_tightened": False,
                    "foldered_canonical_finalized": False,
                },
                "legacy_fallback_review_gate": {
                    "requires_consumer_readiness_recheck": True,
                    "requires_delivery_source_audit_recheck": True,
                },
                "blocking_reasons": [],
                "warnings": [],
            }
            readiness_score = self._ready_foldered_canonical_readiness_score()

            payload = review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_payload(
                default_artifact_root=root,
                post_apply_validation_result_json=json.dumps(validation_result),
                readiness_score_json=json.dumps(readiness_score),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["validation_result_count"], 2)
            self.assertTrue(payload["summary"]["all_promotions_observed"])
            self.assertTrue(payload["summary"]["ready_for_legacy_fallback_tightening_plan_review"])
            self.assertTrue(payload["readiness_checks"]["post_apply_validation_result_verified"])
            self.assertTrue(payload["readiness_checks"]["consumer_readiness_ready_for_foldered_canonical_review"])
            self.assertTrue(payload["tightening_plan_gate"]["plan_tool_implemented"])
            self.assertFalse(payload["tightening_plan_gate"]["allows_legacy_fallback_tightening_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            self.assertIn("review_legacy_fallback_tightening_plan_as_separate_step", payload["recommended_next_actions"])

    def test_legacy_fallback_tightening_plan_blocks_without_ready_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-plan.v1",
            )
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("legacy_fallback_tightening_readiness_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["executor_gate"]["ready_for_legacy_fallback_tightening_executor_review"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_legacy_fallback_tightening_plan_uses_ready_readiness_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            apply_plan, dry_run, physical_preflight, backend_manifest = self._ready_physical_apply_evidence(
                root,
                ["workspace_task_card", "workspace_runtime_context"],
            )
            self._write_physical_apply_evidence_artifacts(
                root,
                apply_plan=apply_plan,
                dry_run=dry_run,
                physical_preflight=physical_preflight,
                backend_manifest=backend_manifest,
            )
            apply_result = execute_workspace_foldered_canonical_physical_apply_payload(
                default_artifact_root=root,
                mode="apply",
                approve_physical_apply=True,
            )
            promoted_manifest = json.loads((root / "workspace" / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            validation = review_workspace_foldered_canonical_migration_post_apply_validation_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                post_apply_backend_manifest_json=json.dumps(promoted_manifest),
            )
            validation_result = record_workspace_foldered_canonical_migration_post_apply_validation_result_payload(
                default_artifact_root=root,
                post_apply_validation_json=json.dumps(validation),
            )
            readiness = review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_payload(
                default_artifact_root=root,
                post_apply_validation_result_json=json.dumps(validation_result),
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
            )

            payload = plan_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_readiness_json=json.dumps(readiness),
                backend_manifest_json=json.dumps(promoted_manifest),
            )

            self.assertEqual(apply_result["status"], "applied")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_tightening_update_count"], 2)
            self.assertTrue(payload["summary"]["plan_only"])
            self.assertTrue(payload["digest_guard"]["legacy_fallback_tightening_plan_digest"])
            self.assertEqual(len(payload["planned_manifest_updates"]), 2)
            for update in payload["planned_manifest_updates"]:
                self.assertEqual(update["status"], "ready_for_legacy_fallback_tightening_plan_review")
                self.assertTrue(update["planned_metadata_update"]["workspace_alias.legacy_fallback_tightening_planned"])
                self.assertFalse(update["mutates_manifest_in_this_tool"])
            self.assertEqual(payload["approval_requirements"]["approval_action"], "foldered_canonical_legacy_fallback_tightening")
            self.assertFalse(payload["approval_requirements"]["records_approval_in_this_tool"])
            self.assertFalse(payload["transaction_journal_plan"]["writes_journal_in_this_tool"])
            self.assertEqual(
                payload["executor_gate"]["preflight_tool"],
                "review_workspace_foldered_canonical_legacy_fallback_tightening_preflight",
            )
            self.assertTrue(payload["executor_gate"]["preflight_tool_implemented"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertFalse(payload["executor_gate"]["allows_legacy_fallback_tightening_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])

    def test_legacy_fallback_tightening_plan_blocks_unknown_requested_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            readiness = {
                "schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-readiness.v1",
                "status": "ready_for_review",
                "tightening_plan_gate": {"ready_for_legacy_fallback_tightening_plan_review": True},
                "blocking_reasons": [],
                "warnings": [],
            }
            manifest = {
                "schema_version": "reverse-deepagent.backend-artifact-manifest.v1",
                "entries": [
                    {
                        "artifact_key": "workspace_task_card",
                        "path": "workspace/review/task-card.json",
                        "metadata": {
                            "workspace_alias": {
                                "future_path": "workspace/review/task-card.json",
                                "legacy_fallback_path": "workspace/task-card.json",
                                "legacy_fallback_preserved": True,
                                "legacy_fallback_tightened": False,
                            }
                        },
                    }
                ],
            }

            payload = plan_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_readiness_json=json.dumps(readiness),
                backend_manifest_json=json.dumps(manifest),
                artifact_keys_json=json.dumps(["missing_key"]),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("unknown_requested_artifact_keys", payload["blocking_reasons"])
            self.assertIn("missing_key", payload["blocked_artifacts"]["unknown_artifact_keys"])

    def test_legacy_fallback_tightening_plan_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            readiness = {
                "schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-readiness.v1",
                "status": "ready_for_review",
                "tightening_plan_gate": {"ready_for_legacy_fallback_tightening_plan_review": True},
                "blocking_reasons": [],
                "warnings": [],
            }
            manifest = {
                "schema_version": "reverse-deepagent.backend-artifact-manifest.v1",
                "entries": [
                    {
                        "artifact_key": "workspace_task_card",
                        "path": "workspace/review/task-card.json",
                        "metadata": {
                            "workspace_alias": {
                                "future_path": "workspace/review/task-card.json",
                                "legacy_fallback_path": "workspace/task-card.json",
                                "legacy_fallback_preserved": True,
                                "legacy_fallback_tightened": False,
                            }
                        },
                    }
                ],
            }
            tool = make_plan_workspace_foldered_canonical_legacy_fallback_tightening_tool(root)

            payload = tool(
                legacy_fallback_tightening_readiness_json=json.dumps(readiness),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(tool.__name__, "plan_workspace_foldered_canonical_legacy_fallback_tightening")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])

    def test_legacy_fallback_tightening_preflight_blocks_without_ready_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-preflight.v1",
            )
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("legacy_fallback_tightening_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("review_approval_ledger_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("review_approval_ledger_missing_matching_legacy_fallback_tightening_approval", payload["blocking_reasons"])
            self.assertFalse(payload["executor_gate"]["ready_for_legacy_fallback_tightening_executor_review"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_legacy_fallback_tightening_preflight_uses_ready_plan_manifest_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(
                root,
                ["workspace_task_card", "workspace_runtime_context"],
            )

            payload = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_tightening_update_count"], 2)
            self.assertEqual(payload["summary"]["manifest_candidate_ready_count"], 2)
            self.assertTrue(payload["summary"]["matching_review_approval_found"])
            self.assertTrue(payload["summary"]["ready_for_legacy_fallback_tightening_executor_review"])
            self.assertFalse(payload["summary"]["legacy_fallback_tightened_by_this_tool"])
            self.assertTrue(payload["digest_guard"]["legacy_fallback_tightening_plan_digest"])
            self.assertTrue(payload["digest_guard"]["digest_matches_approval"])
            self.assertTrue(payload["review_approval_gate"]["approved"])
            self.assertTrue(payload["review_approval_gate"]["digest_matches_expected"])
            self.assertTrue(payload["manifest_revalidation"]["all_candidates_still_ready"])
            self.assertTrue(payload["transaction_journal_plan"]["required"])
            self.assertFalse(payload["transaction_journal_plan"]["writes_journal_in_this_tool"])
            self.assertTrue(payload["idempotency_guard"]["required"])
            self.assertEqual(payload["idempotency_guard"]["idempotency_key"], "idem-legacy-fallback-tightening")
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertFalse(payload["executor_gate"]["allows_manifest_mutation_in_this_tool"])
            self.assertFalse(payload["executor_gate"]["allows_legacy_fallback_tightening_in_this_tool"])
            self.assertTrue(payload["executor_gate"]["requires_finalization_as_separate_follow_up"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])

    def test_legacy_fallback_tightening_preflight_blocks_stale_manifest_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            promoted_manifest["entries"][0]["metadata"]["workspace_alias"]["legacy_fallback_tightened"] = True

            payload = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("backend_manifest_legacy_fallback_candidates_not_ready", payload["blocking_reasons"])
            self.assertFalse(payload["manifest_revalidation"]["all_candidates_still_ready"])
            self.assertEqual(
                payload["manifest_revalidation"]["candidate_results"][0]["status"],
                "blocked_legacy_fallback_already_tightened",
            )

    def test_legacy_fallback_tightening_preflight_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            tool = make_review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_tool(root)

            payload = tool(
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_legacy_fallback_tightening_preflight")
            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-preflight.v1",
            )
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_execute_legacy_fallback_tightening_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )

            payload = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-result.v1")
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["summary"]["planned_tightening_update_count"], 1)
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertFalse(payload["summary"]["legacy_fallback_tightened"])
            self.assertFalse(payload["summary"]["foldered_canonical_finalized"])
            self.assertFalse(payload["transaction_journal"]["entry_appended"])
            self.assertTrue(payload["side_effect_policy"]["dry_run_is_read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-legacy-fallback-tightening-result.json").exists())

    def test_execute_legacy_fallback_tightening_blocks_apply_without_approval_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )

            payload = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_approve_legacy_fallback_tightening_true", payload["blocking_reasons"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_execute_legacy_fallback_tightening_applies_manifest_metadata_with_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(
                root,
                ["workspace_task_card", "workspace_runtime_context"],
            )
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )

            payload = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )

            self.assertEqual(payload["status"], "applied")
            self.assertEqual(payload["summary"]["applied_tightening_update_count"], 2)
            self.assertTrue(payload["summary"]["backend_manifest_mutated"])
            self.assertTrue(payload["summary"]["transaction_journal_written"])
            self.assertTrue(payload["summary"]["result_artifact_written"])
            self.assertTrue(payload["summary"]["legacy_fallback_tightened"])
            self.assertFalse(payload["summary"]["canonical_paths_changed"])
            self.assertFalse(payload["summary"]["foldered_canonical_finalized"])
            self.assertTrue(payload["backend_manifest_mutation"]["tightens_legacy_fallback"])
            self.assertFalse(payload["backend_manifest_mutation"]["changes_canonical_paths"])
            self.assertTrue(payload["transaction_journal"]["entry_appended"])
            self.assertTrue(payload["side_effect_policy"]["artifacts_written"])
            self.assertTrue(payload["side_effect_policy"]["mutates_manifests"])
            self.assertTrue(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            written_manifest = json.loads((root / "workspace" / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            for entry in written_manifest["entries"]:
                alias = entry["metadata"]["workspace_alias"]
                self.assertTrue(alias["legacy_fallback_tightened"])
                self.assertFalse(alias["legacy_fallback_preserved"])
                self.assertEqual(alias["legacy_fallback_status"], "tightened-after-reviewed-apply")
                self.assertNotEqual(entry["path"], alias["legacy_fallback_path"])
            written_result = json.loads(
                (root / "workspace" / "workspace-foldered-canonical-legacy-fallback-tightening-result.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(written_result["status"], "applied")

    def test_execute_legacy_fallback_tightening_blocks_duplicate_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )
            execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )

            payload = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("legacy_fallback_tightening_duplicate_idempotency_key", payload["blocking_reasons"])
            self.assertTrue(payload["idempotency_guard"]["duplicate_entry_found"])

    def test_execute_legacy_fallback_tightening_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )
            tool = make_execute_workspace_foldered_canonical_legacy_fallback_tightening_tool(root)

            payload = tool(
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
            )

            self.assertEqual(tool.__name__, "execute_workspace_foldered_canonical_legacy_fallback_tightening")
            self.assertEqual(payload["status"], "planned")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_finalization_readiness_blocks_without_tightening_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_migration_finalization_readiness_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-migration-finalization-readiness.v1",
            )
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("legacy_fallback_tightening_result_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["finalization_plan_gate"]["ready_for_foldered_canonical_finalization_plan_review"])
            self.assertTrue(payload["finalization_plan_gate"]["plan_tool_implemented"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_finalization_readiness_uses_applied_tightening_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(
                root,
                ["workspace_task_card", "workspace_runtime_context"],
            )
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )
            tightening_result = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )
            tightened_manifest = json.loads((root / "workspace" / "backend-artifact-manifest.json").read_text(encoding="utf-8"))

            payload = review_workspace_foldered_canonical_migration_finalization_readiness_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_result_json=json.dumps(tightening_result),
                backend_manifest_json=json.dumps(tightened_manifest),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["applied_tightening_update_count"], 2)
            self.assertEqual(payload["summary"]["manifest_entry_ready_count"], 2)
            self.assertTrue(payload["summary"]["ready_for_foldered_canonical_finalization_plan_review"])
            self.assertTrue(payload["readiness_checks"]["legacy_fallback_tightening_result_applied"])
            self.assertTrue(payload["readiness_checks"]["all_manifest_entries_tightened"])
            self.assertTrue(payload["readiness_checks"]["canonical_paths_remain_foldered"])
            self.assertTrue(payload["manifest_revalidation"]["all_entries_ready_for_finalization_review"])
            self.assertTrue(payload["finalization_plan_gate"]["plan_tool_implemented"])
            self.assertFalse(payload["finalization_plan_gate"]["allows_finalization_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            self.assertIn("review_foldered_canonical_finalization_plan_as_separate_step", payload["recommended_next_actions"])

    def test_foldered_canonical_finalization_readiness_blocks_stale_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )
            tightening_result = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )

            payload = review_workspace_foldered_canonical_migration_finalization_readiness_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_result_json=json.dumps(tightening_result),
                backend_manifest_json=json.dumps(promoted_manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("manifest_entry:workspace_task_card:legacy_fallback_not_tightened", payload["blocking_reasons"])
            self.assertFalse(payload["manifest_revalidation"]["all_entries_ready_for_finalization_review"])
            self.assertFalse(payload["readiness_checks"]["all_manifest_entries_tightened"])

    def test_foldered_canonical_finalization_readiness_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )
            execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )
            tool = make_review_workspace_foldered_canonical_migration_finalization_readiness_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_migration_finalization_readiness")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["legacy_fallback_tightening_result_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_finalization_plan_blocks_without_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_foldered_canonical_migration_finalization_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-migration-finalization-plan.v1",
            )
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_finalization_readiness_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["executor_gate"]["ready_for_foldered_canonical_finalization_preflight_review"])
            self.assertTrue(payload["executor_gate"]["preflight_tool_implemented"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])

    def test_foldered_canonical_finalization_plan_uses_ready_readiness_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(
                root,
                ["workspace_task_card", "workspace_runtime_context"],
            )
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )
            tightening_result = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )
            tightened_manifest = json.loads((root / "workspace" / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            readiness = review_workspace_foldered_canonical_migration_finalization_readiness_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_result_json=json.dumps(tightening_result),
                backend_manifest_json=json.dumps(tightened_manifest),
            )

            payload = plan_workspace_foldered_canonical_migration_finalization_payload(
                default_artifact_root=root,
                finalization_readiness_json=json.dumps(readiness),
                backend_manifest_json=json.dumps(tightened_manifest),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_finalization_update_count"], 2)
            self.assertTrue(payload["summary"]["plan_only"])
            self.assertTrue(payload["digest_guard"]["foldered_canonical_finalization_plan_digest"])
            self.assertEqual(payload["approval_requirements"]["approval_action"], "foldered_canonical_migration_finalization")
            self.assertTrue(payload["executor_gate"]["ready_for_foldered_canonical_finalization_preflight_review"])
            self.assertTrue(payload["executor_gate"]["preflight_tool_implemented"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertFalse(payload["executor_gate"]["allows_finalization_in_this_tool"])
            self.assertEqual(payload["planned_manifest_updates"][0]["status"], "ready_for_foldered_canonical_finalization_plan_review")
            self.assertFalse(payload["planned_manifest_updates"][0]["mutates_manifest_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            self.assertIn("record_review_approval_before_finalization_preflight", payload["recommended_next_actions"])

    def test_foldered_canonical_finalization_plan_blocks_unknown_requested_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )
            tightening_result = execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )
            tightened_manifest = json.loads((root / "workspace" / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            readiness = review_workspace_foldered_canonical_migration_finalization_readiness_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_result_json=json.dumps(tightening_result),
                backend_manifest_json=json.dumps(tightened_manifest),
            )

            payload = plan_workspace_foldered_canonical_migration_finalization_payload(
                default_artifact_root=root,
                finalization_readiness_json=json.dumps(readiness),
                backend_manifest_json=json.dumps(tightened_manifest),
                artifact_keys_json=json.dumps(["workspace_task_card", "missing_key"]),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("unknown_requested_artifact_keys", payload["blocking_reasons"])
            self.assertIn("missing_key", payload["blocked_artifacts"]["unknown_artifact_keys"])
            self.assertEqual(payload["summary"]["unknown_requested_artifact_key_count"], 1)
            self.assertEqual(payload["planned_manifest_updates"], [])

    def test_foldered_canonical_finalization_plan_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, promoted_manifest = self._ready_legacy_fallback_tightening_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
                default_artifact_root=root,
                legacy_fallback_tightening_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(promoted_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_legacy_fallback_tightening(plan)),
            )
            execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
                default_artifact_root=root,
                mode="apply",
                approve_legacy_fallback_tightening=True,
                legacy_fallback_tightening_preflight_json=json.dumps(preflight),
                legacy_fallback_tightening_plan_json=json.dumps(plan),
            )
            readiness = review_workspace_foldered_canonical_migration_finalization_readiness_payload(
                default_artifact_root=root,
            )
            workspace = root / "workspace"
            (workspace / "workspace-foldered-canonical-migration-finalization-readiness.json").write_text(
                json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tool = make_plan_workspace_foldered_canonical_migration_finalization_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "plan_workspace_foldered_canonical_migration_finalization")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["finalization_readiness_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_finalization_preflight_blocks_without_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-migration-finalization-preflight.v1",
            )
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_finalization_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("review_approval_ledger_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["executor_gate"]["ready_for_foldered_canonical_finalization_executor_review"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_finalization_preflight_uses_ready_plan_manifest_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, tightened_manifest = self._ready_finalization_plan(root, ["workspace_task_card", "workspace_runtime_context"])

            payload = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
                default_artifact_root=root,
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(tightened_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_finalization(plan)),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_finalization_update_count"], 2)
            self.assertEqual(payload["summary"]["manifest_candidate_ready_count"], 2)
            self.assertTrue(payload["summary"]["matching_review_approval_found"])
            self.assertTrue(payload["summary"]["ready_for_foldered_canonical_finalization_executor_review"])
            self.assertTrue(payload["digest_guard"]["digest_matches_approval"])
            self.assertEqual(
                payload["digest_guard"]["foldered_canonical_finalization_plan_digest"],
                plan["digest_guard"]["foldered_canonical_finalization_plan_digest"],
            )
            self.assertTrue(payload["review_approval_gate"]["approved"])
            self.assertTrue(payload["review_approval_gate"]["digest_matches_expected"])
            self.assertTrue(payload["manifest_revalidation"]["all_candidates_still_ready"])
            self.assertTrue(payload["transaction_journal_plan"]["required"])
            self.assertFalse(payload["transaction_journal_plan"]["writes_journal_in_this_tool"])
            self.assertTrue(payload["idempotency_guard"]["required"])
            self.assertFalse(payload["idempotency_guard"]["checks_existing_finalization_journal_in_this_tool"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertFalse(payload["executor_gate"]["allows_finalization_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            self.assertIn("run_separate_explicit_finalization_executor_with_transaction_journal", payload["recommended_next_actions"])

    def test_foldered_canonical_finalization_preflight_blocks_stale_manifest_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, tightened_manifest = self._ready_finalization_plan(root, ["workspace_task_card"])
            stale_manifest = json.loads(json.dumps(tightened_manifest))
            stale_manifest["entries"][0]["metadata"]["workspace_alias"]["legacy_fallback_tightened"] = False

            payload = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
                default_artifact_root=root,
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(stale_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_finalization(plan)),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("backend_manifest_finalization_candidates_not_ready", payload["blocking_reasons"])
            self.assertFalse(payload["manifest_revalidation"]["all_candidates_still_ready"])
            self.assertEqual(
                payload["manifest_revalidation"]["candidate_results"][0]["status"],
                "blocked_legacy_fallback_not_tightened",
            )

    def test_foldered_canonical_finalization_preflight_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, tightened_manifest = self._ready_finalization_plan(root, ["workspace_task_card"])
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-migration-finalization-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(tightened_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "review-approval-ledger.json").write_text(
                json.dumps(self._approval_ledger_for_finalization(plan), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tool = make_review_workspace_foldered_canonical_migration_finalization_preflight_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_migration_finalization_preflight")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["finalization_plan_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertEqual(payload["review_approval_ledger_input"]["source"], "artifact-ref")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_execute_foldered_canonical_finalization_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, tightened_manifest = self._ready_finalization_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
                default_artifact_root=root,
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(tightened_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_finalization(plan)),
            )

            payload = execute_workspace_foldered_canonical_migration_finalization_payload(
                default_artifact_root=root,
                finalization_preflight_json=json.dumps(preflight),
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(tightened_manifest),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-finalization-result.v1")
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["mode"], "dry-run")
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertFalse(payload["summary"]["foldered_canonical_finalized"])
            self.assertIn("foldered_canonical_finalization_dry_run_does_not_write_journal_result_or_manifest", payload["warnings"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(payload["side_effect_policy"]["writes_result_artifact"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["finalizes_foldered_canonical_migration"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-finalization-result.json").exists())
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-finalization-journal.json").exists())

    def test_execute_foldered_canonical_finalization_blocks_apply_without_approval_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, tightened_manifest = self._ready_finalization_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
                default_artifact_root=root,
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(tightened_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_finalization(plan)),
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-migration-finalization-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-migration-finalization-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(tightened_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            payload = execute_workspace_foldered_canonical_migration_finalization_payload(
                default_artifact_root=root,
                mode="apply",
                approve_finalization=False,
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_approve_finalization_true", payload["blocking_reasons"])
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((workspace / "workspace-foldered-canonical-migration-finalization-result.json").exists())
            self.assertFalse((workspace / "workspace-foldered-canonical-migration-finalization-journal.json").exists())

    def test_execute_foldered_canonical_finalization_applies_manifest_metadata_with_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, tightened_manifest = self._ready_finalization_plan(root, ["workspace_task_card"])
            original_canonical_path = tightened_manifest["entries"][0]["path"]
            preflight = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
                default_artifact_root=root,
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(tightened_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_finalization(plan)),
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-migration-finalization-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-migration-finalization-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(tightened_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            payload = execute_workspace_foldered_canonical_migration_finalization_payload(
                default_artifact_root=root,
                mode="apply",
                approve_finalization=True,
            )

            self.assertEqual(payload["status"], "applied")
            self.assertTrue(payload["summary"]["result_artifact_written"])
            self.assertTrue(payload["summary"]["backend_manifest_mutated"])
            self.assertTrue(payload["summary"]["transaction_journal_written"])
            self.assertTrue(payload["summary"]["foldered_canonical_finalized"])
            self.assertFalse(payload["summary"]["canonical_paths_changed"])
            self.assertFalse(payload["summary"]["files_moved"])
            self.assertTrue(payload["side_effect_policy"]["artifacts_written"])
            self.assertTrue(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertTrue(payload["side_effect_policy"]["writes_result_artifact"])
            self.assertTrue(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertTrue((workspace / "workspace-foldered-canonical-migration-finalization-result.json").exists())
            self.assertTrue((workspace / "workspace-foldered-canonical-migration-finalization-journal.json").exists())

            written_manifest = json.loads((workspace / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(written_manifest["entries"][0]["path"], original_canonical_path)
            alias = written_manifest["entries"][0]["metadata"]["workspace_alias"]
            self.assertTrue(alias["foldered_canonical_finalization_planned"])
            self.assertTrue(alias["foldered_canonical_finalized"])
            self.assertEqual(alias["migration_status"], "foldered-canonical-finalized-after-reviewed-apply")
            self.assertEqual(alias["resolver_migration_status"], "foldered-canonical-authoritative")
            self.assertTrue(alias["legacy_fallback_tightened"])
            self.assertFalse(alias["legacy_fallback_preserved"])
            self.assertEqual(
                written_manifest["metadata"]["foldered_canonical_finalization_transaction_id"],
                payload["summary"]["transaction_id"],
            )

            journal = json.loads((workspace / "workspace-foldered-canonical-migration-finalization-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(len(journal["entries"]), 1)
            self.assertEqual(journal["entries"][0]["status"], "applied")
            self.assertEqual(journal["entries"][0]["idempotency_key"], "idem-foldered-finalization")
            result = json.loads((workspace / "workspace-foldered-canonical-migration-finalization-result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "applied")
            self.assertTrue(result["summary"]["result_artifact_written"])

    def test_execute_foldered_canonical_finalization_blocks_duplicate_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, tightened_manifest = self._ready_finalization_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
                default_artifact_root=root,
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(tightened_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_finalization(plan)),
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-migration-finalization-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-migration-finalization-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(tightened_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            first = execute_workspace_foldered_canonical_migration_finalization_payload(
                default_artifact_root=root,
                mode="apply",
                approve_finalization=True,
            )
            second = execute_workspace_foldered_canonical_migration_finalization_payload(
                default_artifact_root=root,
                mode="apply",
                approve_finalization=True,
            )

            self.assertEqual(first["status"], "applied")
            self.assertEqual(second["status"], "blocked")
            self.assertIn("foldered_canonical_finalization_duplicate_idempotency_key", second["blocking_reasons"])
            self.assertTrue(second["idempotency_guard"]["duplicate_entry_found"])
            self.assertFalse(second["summary"]["result_artifact_written"])

    def test_execute_foldered_canonical_finalization_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, tightened_manifest = self._ready_finalization_plan(root, ["workspace_task_card"])
            preflight = review_workspace_foldered_canonical_migration_finalization_preflight_payload(
                default_artifact_root=root,
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(tightened_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_finalization(plan)),
            )
            tool = make_execute_workspace_foldered_canonical_migration_finalization_tool(root)

            payload = tool(
                finalization_preflight_json=json.dumps(preflight),
                finalization_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(tightened_manifest),
            )

            self.assertEqual(tool.__name__, "execute_workspace_foldered_canonical_migration_finalization")
            self.assertEqual(payload["status"], "planned")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_post_finalization_audit_blocks_without_result_journal_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-migration-post-finalization-audit.v1",
            )
            self.assertEqual(payload["status"], "not_ready")
            self.assertIn("finalization_result_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("finalization_journal_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["summary"]["artifacts_written"])
            self.assertFalse(payload["rollout_gate"]["broader_rollout_allowed_by_this_tool"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_post_finalization_audit_verifies_applied_result_journal_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            result, journal, manifest = self._applied_finalization_evidence(root, ["workspace_task_card"])

            payload = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
                finalization_result_json=json.dumps(result),
                finalization_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "verified")
            self.assertEqual(payload["summary"]["audit_result_count"], 1)
            self.assertEqual(payload["summary"]["verified_audit_result_count"], 1)
            self.assertTrue(payload["summary"]["all_finalized_entries_verified"])
            self.assertTrue(payload["summary"]["matching_journal_entry_found"])
            self.assertTrue(payload["summary"]["backend_manifest_transaction_metadata_matches"])
            self.assertFalse(payload["summary"]["canonical_paths_changed_by_finalization"])
            self.assertFalse(payload["summary"]["files_moved_by_finalization"])
            self.assertFalse(payload["summary"]["legacy_fallback_tightened_by_finalization"])
            self.assertTrue(payload["journal_audit"]["matching_entry_found"])
            self.assertTrue(payload["backend_manifest_metadata_audit"]["transaction_id_matches_result"])
            self.assertEqual(payload["audit_results"][0]["status"], "verified")
            self.assertTrue(payload["audit_results"][0]["foldered_canonical_finalized"])
            self.assertEqual(payload["audit_results"][0]["resolver_migration_status"], "foldered-canonical-authoritative")
            self.assertTrue(payload["audit_results"][0]["canonical_path_stable_after_finalization"])
            self.assertFalse(payload["rollout_gate"]["broader_rollout_allowed_by_this_tool"])
            self.assertFalse(payload["rollout_gate"]["automatic_materialization_allowed"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["authorizes_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_post_finalization_audit_blocks_manifest_regression_to_legacy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            result, journal, manifest = self._applied_finalization_evidence(root, ["workspace_task_card"])
            regressed_manifest = json.loads(json.dumps(manifest))
            alias = regressed_manifest["entries"][0]["metadata"]["workspace_alias"]
            regressed_manifest["entries"][0]["path"] = alias["legacy_fallback_path"]

            payload = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
                finalization_result_json=json.dumps(result),
                finalization_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(regressed_manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertTrue(
                any(
                    reason.startswith("post_finalization_audit:workspace_task_card:blocked_canonical_path")
                    for reason in payload["blocking_reasons"]
                )
            )
            self.assertTrue(payload["audit_results"][0]["canonical_path_regressed_to_legacy"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_post_finalization_audit_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            self._applied_finalization_evidence(root, ["workspace_task_card"])
            tool = make_review_workspace_foldered_canonical_migration_post_finalization_audit_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_migration_post_finalization_audit")
            self.assertEqual(payload["status"], "verified")
            self.assertEqual(payload["finalization_result_input"]["source"], "artifact-ref")
            self.assertEqual(payload["finalization_journal_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-post-finalization-audit.json").exists())

    def test_broader_rollout_readiness_blocks_without_required_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_broader_rollout_readiness_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-readiness.v1",
            )
            self.assertEqual(payload["status"], "not_ready")
            self.assertIn("post_finalization_audit_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("workspace_consumer_readiness_score_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("delivery_source_audit_recheck_missing", payload["blocking_reasons"])
            self.assertIn("workspace_dual_write_expansion_result_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["summary"]["broader_rollout_review_allowed"])
            self.assertFalse(payload["rollout_gate"]["broader_rollout_apply_allowed_by_this_tool"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["authorizes_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_broader_rollout_readiness_uses_verified_audit_readiness_expansion_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            result, journal, manifest = self._applied_finalization_evidence(root, ["workspace_task_card"])
            audit = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
                finalization_result_json=json.dumps(result),
                finalization_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            delivery_source_audit = {
                "schema_version": "reverse-deepagent.delivery-source-audit.v1",
                "artifact_count": 1,
                "source_artifact_ref_count": 1,
                "source_path_count": 0,
                "workspace_resolved_count": 1,
                "external_source_path_count": 0,
            }

            payload = review_workspace_foldered_canonical_broader_rollout_readiness_payload(
                default_artifact_root=root,
                post_finalization_audit_json=json.dumps(audit),
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                delivery_source_audit_json=json.dumps(delivery_source_audit),
                expansion_result_json=json.dumps(expansion_result),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["summary"]["broader_rollout_review_allowed"])
            self.assertFalse(payload["summary"]["broader_rollout_authorized_by_this_tool"])
            self.assertTrue(payload["readiness_checks"]["post_finalization_audit_verified"])
            self.assertTrue(payload["readiness_checks"]["consumer_readiness_ready_for_foldered_canonical_review"])
            self.assertTrue(payload["readiness_checks"]["delivery_source_recheck_clean"])
            self.assertTrue(payload["readiness_checks"]["dual_write_expansion_result_verified"])
            self.assertTrue(payload["readiness_checks"]["manifest_finalization_metadata_observed"])
            self.assertTrue(payload["rollout_gate"]["broader_rollout_plan_allowed_for_review"])
            self.assertFalse(payload["rollout_gate"]["broader_rollout_apply_allowed_by_this_tool"])
            self.assertFalse(payload["rollout_gate"]["automatic_materialization_allowed"])
            self.assertIn("readiness_descriptor_does_not_authorize_broader_rollout_apply", payload["warnings"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_broader_rollout_readiness_blocks_source_path_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            result, journal, manifest = self._applied_finalization_evidence(root, ["workspace_task_card"])
            audit = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
                finalization_result_json=json.dumps(result),
                finalization_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            delivery_source_audit = {
                "schema_version": "reverse-deepagent.delivery-source-audit.v1",
                "artifact_count": 1,
                "source_artifact_ref_count": 0,
                "source_path_count": 1,
                "workspace_resolved_count": 0,
                "external_source_path_count": 1,
            }

            payload = review_workspace_foldered_canonical_broader_rollout_readiness_payload(
                default_artifact_root=root,
                post_finalization_audit_json=json.dumps(audit),
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                delivery_source_audit_json=json.dumps(delivery_source_audit),
                expansion_result_json=json.dumps(expansion_result),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("delivery_source_audit_source_path_usage_observed", payload["blocking_reasons"])
            self.assertIn("delivery_source_audit_external_source_path_usage_observed", payload["blocking_reasons"])
            self.assertFalse(payload["readiness_checks"]["delivery_source_recheck_clean"])
            self.assertFalse(payload["rollout_gate"]["broader_rollout_plan_allowed_for_review"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_broader_rollout_readiness_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            result, journal, manifest = self._applied_finalization_evidence(root, ["workspace_task_card"])
            audit = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
                finalization_result_json=json.dumps(result),
                finalization_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            (workspace / "workspace-foldered-canonical-migration-post-finalization-audit.json").write_text(
                json.dumps(audit),
                encoding="utf-8",
            )
            (workspace / "workspace-consumer-readiness-score.json").write_text(
                json.dumps(self._ready_foldered_canonical_readiness_score()),
                encoding="utf-8",
            )
            (workspace / "workspace-dual-write-expansion-result.json").write_text(json.dumps(expansion_result), encoding="utf-8")
            tool = make_review_workspace_foldered_canonical_broader_rollout_readiness_tool(root)

            payload = tool(
                delivery_source_audit_json=json.dumps(
                    {
                        "schema_version": "reverse-deepagent.delivery-source-audit.v1",
                        "artifact_count": 1,
                        "source_artifact_ref_count": 1,
                        "source_path_count": 0,
                        "workspace_resolved_count": 1,
                        "external_source_path_count": 0,
                    }
                )
            )

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_broader_rollout_readiness")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["post_finalization_audit_input"]["source"], "artifact-ref")
            self.assertEqual(payload["readiness_score_input"]["source"], "artifact-ref")
            self.assertEqual(payload["expansion_result_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-readiness.json").exists())

    def test_broader_rollout_plan_blocks_without_readiness_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_foldered_canonical_broader_rollout_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-plan.v1",
            )
            self.assertEqual(payload["status"], "not_ready")
            self.assertIn("broader_rollout_readiness_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("broader_rollout_readiness_not_ready_for_plan", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["executor_gate"]["ready_for_broader_rollout_apply_review"])
            self.assertTrue(payload["executor_gate"]["preflight_tool_implemented"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_broader_rollout_plan_uses_ready_readiness_and_finalized_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            result, journal, manifest = self._applied_finalization_evidence(root, ["workspace_task_card"])
            audit = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
                finalization_result_json=json.dumps(result),
                finalization_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            readiness = review_workspace_foldered_canonical_broader_rollout_readiness_payload(
                default_artifact_root=root,
                post_finalization_audit_json=json.dumps(audit),
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                delivery_source_audit_json=json.dumps(
                    {
                        "schema_version": "reverse-deepagent.delivery-source-audit.v1",
                        "artifact_count": 1,
                        "source_artifact_ref_count": 1,
                        "source_path_count": 0,
                        "workspace_resolved_count": 1,
                        "external_source_path_count": 0,
                    }
                ),
                expansion_result_json=json.dumps(expansion_result),
                backend_manifest_json=json.dumps(manifest),
            )

            payload = plan_workspace_foldered_canonical_broader_rollout_payload(
                default_artifact_root=root,
                broader_rollout_readiness_json=json.dumps(readiness),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["candidate_count"], 1)
            self.assertEqual(payload["summary"]["ready_candidate_count"], 1)
            self.assertEqual(payload["summary"]["blocked_candidate_count"], 0)
            self.assertEqual(payload["candidate_artifacts"][0]["artifact_key"], "workspace_task_card")
            self.assertEqual(payload["candidate_artifacts"][0]["status"], "ready_for_broader_rollout_plan_review")
            self.assertEqual(payload["candidate_artifacts"][0]["risk"]["risk_level"], "low")
            self.assertTrue(payload["digest_guard"]["broader_rollout_plan_digest"])
            self.assertTrue(payload["digest_guard"]["requires_plan_digest_match_before_apply"])
            self.assertTrue(payload["approval_requirements"]["required_before_apply"])
            self.assertFalse(payload["approval_requirements"]["records_approval_in_this_tool"])
            self.assertTrue(payload["executor_gate"]["ready_for_broader_rollout_apply_review"])
            self.assertTrue(payload["executor_gate"]["preflight_tool_implemented"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertFalse(payload["executor_gate"]["allows_rollout_apply_in_this_tool"])
            self.assertIn("broader_rollout_plan_is_review_only_and_does_not_authorize_apply", payload["warnings"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["authorizes_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["applies_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-plan.json").exists())

    def test_broader_rollout_plan_blocks_unknown_requested_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            result, journal, manifest = self._applied_finalization_evidence(root, ["workspace_task_card"])
            audit = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
                finalization_result_json=json.dumps(result),
                finalization_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            readiness = review_workspace_foldered_canonical_broader_rollout_readiness_payload(
                default_artifact_root=root,
                post_finalization_audit_json=json.dumps(audit),
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                delivery_source_audit_json=json.dumps(
                    {
                        "schema_version": "reverse-deepagent.delivery-source-audit.v1",
                        "artifact_count": 1,
                        "source_artifact_ref_count": 1,
                        "source_path_count": 0,
                        "workspace_resolved_count": 1,
                        "external_source_path_count": 0,
                    }
                ),
                expansion_result_json=json.dumps(expansion_result),
                backend_manifest_json=json.dumps(manifest),
            )

            payload = plan_workspace_foldered_canonical_broader_rollout_payload(
                default_artifact_root=root,
                broader_rollout_readiness_json=json.dumps(readiness),
                backend_manifest_json=json.dumps(manifest),
                artifact_keys_json=json.dumps(["missing_workspace_artifact"]),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("unknown_requested_artifact_keys", payload["blocking_reasons"])
            self.assertIn("no_broader_rollout_candidates_selected", payload["blocking_reasons"])
            self.assertEqual(payload["blocked_artifacts"]["unknown_artifact_keys"], ["missing_workspace_artifact"])
            self.assertFalse(payload["executor_gate"]["ready_for_broader_rollout_apply_review"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_broader_rollout_plan_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            result, journal, manifest = self._applied_finalization_evidence(root, ["workspace_task_card"])
            audit = review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
                default_artifact_root=root,
                finalization_result_json=json.dumps(result),
                finalization_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )
            expansion_plan = self._ready_workspace_dual_write_expansion_plan(root, ["workspace_task_card"])
            expansion_result = self._verified_workspace_dual_write_expansion_result(expansion_plan)
            readiness = review_workspace_foldered_canonical_broader_rollout_readiness_payload(
                default_artifact_root=root,
                post_finalization_audit_json=json.dumps(audit),
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
                delivery_source_audit_json=json.dumps(
                    {
                        "schema_version": "reverse-deepagent.delivery-source-audit.v1",
                        "artifact_count": 1,
                        "source_artifact_ref_count": 1,
                        "source_path_count": 0,
                        "workspace_resolved_count": 1,
                        "external_source_path_count": 0,
                    }
                ),
                expansion_result_json=json.dumps(expansion_result),
                backend_manifest_json=json.dumps(manifest),
            )
            (workspace / "workspace-foldered-canonical-broader-rollout-readiness.json").write_text(
                json.dumps(readiness),
                encoding="utf-8",
            )
            tool = make_plan_workspace_foldered_canonical_broader_rollout_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "plan_workspace_foldered_canonical_broader_rollout")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["broader_rollout_readiness_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertEqual(payload["summary"]["ready_candidate_count"], 1)
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-plan.json").exists())

    def test_broader_rollout_preflight_blocks_without_plan_manifest_or_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_broader_rollout_preflight_payload(
                default_artifact_root=root,
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-preflight.v1",
            )
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("broader_rollout_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("review_approval_ledger_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["executor_gate"]["ready_for_broader_rollout_executor_review"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["applies_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_broader_rollout_preflight_uses_ready_plan_manifest_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, manifest = self._ready_broader_rollout_plan(root, ["workspace_task_card"])

            payload = review_workspace_foldered_canonical_broader_rollout_preflight_payload(
                default_artifact_root=root,
                broader_rollout_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_broader_rollout(plan)),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_broader_rollout_candidate_count"], 1)
            self.assertEqual(payload["summary"]["manifest_candidate_ready_count"], 1)
            self.assertTrue(payload["summary"]["matching_review_approval_found"])
            self.assertTrue(payload["summary"]["ready_for_broader_rollout_executor_review"])
            self.assertTrue(payload["digest_guard"]["digest_matches_approval"])
            self.assertEqual(
                payload["digest_guard"]["broader_rollout_plan_digest"],
                plan["digest_guard"]["broader_rollout_plan_digest"],
            )
            self.assertTrue(payload["review_approval_gate"]["approved"])
            self.assertTrue(payload["review_approval_gate"]["digest_matches_expected"])
            self.assertTrue(payload["manifest_revalidation"]["all_candidates_still_ready"])
            self.assertEqual(
                payload["manifest_revalidation"]["candidate_results"][0]["status"],
                "ready_for_broader_rollout_executor_preflight",
            )
            self.assertTrue(payload["transaction_journal_plan"]["required"])
            self.assertFalse(payload["transaction_journal_plan"]["writes_journal_in_this_tool"])
            self.assertTrue(payload["idempotency_guard"]["required"])
            self.assertFalse(payload["idempotency_guard"]["checks_existing_broader_rollout_journal_in_this_tool"])
            self.assertTrue(payload["executor_gate"]["executor_tool_implemented"])
            self.assertFalse(payload["executor_gate"]["allows_broader_rollout_apply_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["applies_broader_rollout"])
            self.assertIn(
                "review_broader_rollout_preflight_before_running_separate_executor",
                payload["recommended_next_actions"],
            )

    def test_broader_rollout_preflight_blocks_stale_manifest_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, manifest = self._ready_broader_rollout_plan(root, ["workspace_task_card"])
            stale_manifest = json.loads(json.dumps(manifest))
            stale_manifest["entries"][0]["metadata"]["workspace_alias"]["foldered_canonical_finalized"] = False

            payload = review_workspace_foldered_canonical_broader_rollout_preflight_payload(
                default_artifact_root=root,
                broader_rollout_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(stale_manifest),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_broader_rollout(plan)),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("backend_manifest_broader_rollout_candidates_not_ready", payload["blocking_reasons"])
            self.assertFalse(payload["manifest_revalidation"]["all_candidates_still_ready"])
            self.assertEqual(
                payload["manifest_revalidation"]["candidate_results"][0]["status"],
                "blocked_not_foldered_canonical_finalized",
            )
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_broader_rollout_preflight_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan, manifest = self._ready_broader_rollout_plan(root, ["workspace_task_card"])
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "review-approval-ledger.json").write_text(
                json.dumps(self._approval_ledger_for_broader_rollout(plan), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tool = make_review_workspace_foldered_canonical_broader_rollout_preflight_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_broader_rollout_preflight")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["broader_rollout_plan_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertEqual(payload["review_approval_ledger_input"]["source"], "artifact-ref")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-preflight.json").exists())

    def test_execute_broader_rollout_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight, plan, manifest = self._ready_broader_rollout_preflight(root, ["workspace_task_card"])
            workspace = root / "workspace"

            payload = execute_workspace_foldered_canonical_broader_rollout_payload(
                default_artifact_root=root,
                broader_rollout_preflight_json=json.dumps(preflight),
                broader_rollout_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-result.v1",
            )
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["mode"], "dry-run")
            self.assertEqual(payload["summary"]["planned_broader_rollout_candidate_count"], 1)
            self.assertFalse(payload["summary"]["transaction_journal_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["summary"]["broader_rollout_applied"])
            self.assertFalse(payload["summary"]["dual_write_enabled"])
            self.assertFalse(payload["summary"]["canonical_paths_changed"])
            self.assertTrue(payload["side_effect_policy"]["dry_run_is_read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(payload["side_effect_policy"]["writes_result_artifact"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["applies_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["sends_cdp_commands"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])
            self.assertIn("review_dry_run_then_rerun_apply_with_explicit_approval", payload["recommended_next_actions"])
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-result.json").exists())
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-journal.json").exists())

    def test_execute_broader_rollout_blocks_apply_without_approval_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight, plan, manifest = self._ready_broader_rollout_preflight(root, ["workspace_task_card"])
            workspace = root / "workspace"

            payload = execute_workspace_foldered_canonical_broader_rollout_payload(
                default_artifact_root=root,
                mode="apply",
                approve_broader_rollout=False,
                broader_rollout_preflight_json=json.dumps(preflight),
                broader_rollout_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_approve_broader_rollout_true", payload["blocking_reasons"])
            self.assertIn("apply_requires_backend_manifest_artifact_ref_not_inline_json", payload["blocking_reasons"])
            self.assertFalse(payload["summary"]["transaction_journal_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["applies_broader_rollout"])
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-result.json").exists())
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-journal.json").exists())

    def test_execute_broader_rollout_applies_manifest_metadata_with_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight, plan, manifest = self._ready_broader_rollout_preflight(root, ["workspace_task_card"])
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            original_path = manifest["entries"][0]["path"]
            (workspace / "workspace-foldered-canonical-broader-rollout-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-broader-rollout-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            payload = execute_workspace_foldered_canonical_broader_rollout_payload(
                default_artifact_root=root,
                mode="apply",
                approve_broader_rollout=True,
            )

            self.assertEqual(payload["status"], "applied")
            self.assertEqual(payload["mode"], "apply")
            self.assertTrue(payload["summary"]["transaction_journal_written"])
            self.assertTrue(payload["summary"]["backend_manifest_mutated"])
            self.assertTrue(payload["summary"]["result_artifact_written"])
            self.assertTrue(payload["summary"]["broader_rollout_applied"])
            self.assertFalse(payload["summary"]["dual_write_enabled"])
            self.assertFalse(payload["summary"]["canonical_paths_changed"])
            self.assertTrue(payload["side_effect_policy"]["artifacts_written"])
            self.assertTrue(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertTrue(payload["side_effect_policy"]["writes_result_artifact"])
            self.assertTrue(payload["side_effect_policy"]["mutates_manifests"])
            self.assertTrue(payload["side_effect_policy"]["applies_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["sends_cdp_commands"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])
            self.assertTrue((workspace / "workspace-foldered-canonical-broader-rollout-result.json").exists())
            self.assertTrue((workspace / "workspace-foldered-canonical-broader-rollout-journal.json").exists())

            written_result = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-result.json").read_text(encoding="utf-8"))
            journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-journal.json").read_text(encoding="utf-8"))
            mutated_manifest = json.loads((workspace / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(written_result["summary"]["transaction_id"], payload["summary"]["transaction_id"])
            self.assertEqual(journal["entry_count"], 1)
            self.assertEqual(journal["entries"][0]["status"], "applied")
            self.assertEqual(journal["entries"][0]["idempotency_key"], payload["summary"]["idempotency_key"])
            self.assertEqual(mutated_manifest["entries"][0]["path"], original_path)
            alias = mutated_manifest["entries"][0]["metadata"]["workspace_alias"]
            self.assertTrue(alias["broader_rollout_planned"])
            self.assertTrue(alias["broader_rollout_applied"])
            self.assertEqual(alias["broader_rollout_transaction_id"], payload["summary"]["transaction_id"])
            self.assertEqual(alias["broader_rollout_canonical_path_confirmed"], original_path)
            self.assertEqual(
                mutated_manifest["metadata"]["foldered_canonical_broader_rollout_transaction_id"],
                payload["summary"]["transaction_id"],
            )

    def test_execute_broader_rollout_blocks_duplicate_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight, plan, manifest = self._ready_broader_rollout_preflight(root, ["workspace_task_card"])
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-broader-rollout-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            first = execute_workspace_foldered_canonical_broader_rollout_payload(
                default_artifact_root=root,
                mode="apply",
                approve_broader_rollout=True,
            )

            second = execute_workspace_foldered_canonical_broader_rollout_payload(
                default_artifact_root=root,
                mode="apply",
                approve_broader_rollout=True,
            )

            self.assertEqual(first["status"], "applied")
            self.assertEqual(second["status"], "blocked")
            self.assertIn("broader_rollout_duplicate_idempotency_key", second["blocking_reasons"])
            self.assertTrue(second["idempotency_guard"]["duplicate_entry_found"])
            journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(journal["entry_count"], 1)

    def test_execute_broader_rollout_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight, plan, manifest = self._ready_broader_rollout_preflight(root, ["workspace_task_card"])
            tool = make_execute_workspace_foldered_canonical_broader_rollout_tool(root)

            payload = tool(
                broader_rollout_preflight_json=json.dumps(preflight),
                broader_rollout_plan_json=json.dumps(plan),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(tool.__name__, "execute_workspace_foldered_canonical_broader_rollout")
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["mode"], "dry-run")
            self.assertEqual(payload["broader_rollout_preflight_input"]["source"], "inline-json")
            self.assertEqual(payload["broader_rollout_plan_input"]["source"], "inline-json")
            self.assertEqual(payload["backend_manifest_input"]["source"], "inline-json")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])

    def test_broader_rollout_post_audit_blocks_without_result_journal_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_broader_rollout_post_audit_payload(default_artifact_root=root)

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-post-audit.v1",
            )
            self.assertEqual(payload["status"], "not_ready")
            self.assertIn("broader_rollout_result_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("broader_rollout_journal_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["summary"]["artifacts_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated_by_this_tool"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["sends_cdp_commands"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-post-audit.json").exists())

    def test_broader_rollout_post_audit_verifies_applied_result_journal_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            result, journal, manifest = self._applied_broader_rollout_evidence(root, ["workspace_task_card"])

            payload = review_workspace_foldered_canonical_broader_rollout_post_audit_payload(
                default_artifact_root=root,
                broader_rollout_result_json=json.dumps(result),
                broader_rollout_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "verified")
            self.assertEqual(payload["summary"]["audit_result_count"], 1)
            self.assertEqual(payload["summary"]["verified_audit_result_count"], 1)
            self.assertTrue(payload["summary"]["all_broader_rollout_entries_verified"])
            self.assertTrue(payload["summary"]["matching_journal_entry_found"])
            self.assertTrue(payload["summary"]["backend_manifest_transaction_metadata_matches"])
            self.assertFalse(payload["summary"]["canonical_paths_changed_by_broader_rollout"])
            self.assertFalse(payload["summary"]["dual_write_enabled_by_broader_rollout"])
            self.assertFalse(payload["summary"]["files_moved_by_broader_rollout"])
            self.assertTrue(payload["journal_audit"]["matching_entry_found"])
            self.assertTrue(payload["backend_manifest_metadata_audit"]["transaction_id_matches_result"])
            self.assertEqual(payload["audit_results"][0]["status"], "verified")
            self.assertTrue(payload["audit_results"][0]["broader_rollout_applied"])
            self.assertTrue(payload["audit_results"][0]["canonical_path_stable_after_broader_rollout"])
            self.assertTrue(payload["post_rollout_gate"]["post_rollout_review_ready"])
            self.assertFalse(payload["post_rollout_gate"]["rollback_vs_commit_decision_allowed_by_this_tool"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["decides_rollback_vs_commit"])

    def test_broader_rollout_post_audit_blocks_manifest_regression_to_legacy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            result, journal, manifest = self._applied_broader_rollout_evidence(root, ["workspace_task_card"])
            alias = manifest["entries"][0]["metadata"]["workspace_alias"]
            manifest["entries"][0]["path"] = alias["legacy_fallback_path"]

            payload = review_workspace_foldered_canonical_broader_rollout_post_audit_payload(
                default_artifact_root=root,
                broader_rollout_result_json=json.dumps(result),
                broader_rollout_journal_json=json.dumps(journal),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn(
                "broader_rollout_post_audit:workspace_task_card:blocked_canonical_path_regressed_to_legacy",
                payload["blocking_reasons"],
            )
            self.assertTrue(payload["audit_results"][0]["canonical_path_regressed_to_legacy"])
            self.assertFalse(payload["post_rollout_gate"]["post_rollout_review_ready"])

    def test_broader_rollout_post_audit_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            self._applied_broader_rollout_evidence(root, ["workspace_task_card"])
            workspace = root / "workspace"
            tool = make_review_workspace_foldered_canonical_broader_rollout_post_audit_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_broader_rollout_post_audit")
            self.assertEqual(payload["status"], "verified")
            self.assertEqual(payload["broader_rollout_result_input"]["source"], "artifact-ref")
            self.assertEqual(payload["broader_rollout_journal_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-post-audit.json").exists())

    def test_broader_rollout_rollback_decision_blocks_without_post_audit_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(default_artifact_root=root)

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-rollback-decision-plan.v1",
            )
            self.assertEqual(payload["status"], "not_ready")
            self.assertIn("broader_rollout_post_audit_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["decision_gate"]["decision_review_ready"])
            self.assertFalse(payload["decision_gate"]["automatic_commit_allowed"])
            self.assertFalse(payload["decision_gate"]["automatic_rollback_allowed"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["records_decision"])
            self.assertFalse(payload["side_effect_policy"]["commits_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])

    def test_broader_rollout_rollback_decision_plan_uses_verified_post_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])

            payload = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["requested_decision"], "commit")
            self.assertEqual(payload["summary"]["selected_decision"], "commit")
            self.assertTrue(payload["summary"]["decision_review_ready"])
            self.assertEqual(payload["summary"]["current_manifest_check_count"], 1)
            self.assertTrue(payload["summary"]["all_current_manifest_checks_verified"])
            self.assertTrue(payload["decision_gate"]["decision_review_ready"])
            self.assertTrue(payload["decision_gate"]["commit_review_allowed"])
            self.assertTrue(payload["decision_gate"]["rollback_review_allowed"])
            self.assertFalse(payload["decision_gate"]["decision_record_allowed_by_this_tool"])
            self.assertTrue(payload["decision_gate"]["requires_separate_decision_record"])
            self.assertTrue(payload["decision_gate"]["requires_separate_commit_or_rollback_executor"])
            self.assertEqual(payload["current_manifest_checks"][0]["status"], "verified")
            self.assertTrue(payload["current_manifest_checks"][0]["canonical_path_stable"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["records_decision"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertIn("record_separate_review_decision_before_any_commit_or_rollback_executor", payload["recommended_next_actions"])

    def test_broader_rollout_rollback_decision_blocks_current_manifest_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            alias = manifest["entries"][0]["metadata"]["workspace_alias"]
            manifest["entries"][0]["path"] = alias["legacy_fallback_path"]

            payload = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn(
                "broader_rollout_rollback_decision:workspace_task_card:blocked_current_manifest_canonical_path_regressed_to_legacy",
                payload["blocking_reasons"],
            )
            self.assertFalse(payload["decision_gate"]["decision_review_ready"])
            self.assertTrue(payload["current_manifest_checks"][0]["canonical_path_regressed_to_legacy"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])

    def test_broader_rollout_rollback_decision_blocks_unsupported_requested_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])

            payload = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="ship-it",
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("requested_decision_not_supported", payload["blocking_reasons"])
            self.assertFalse(payload["decision_gate"]["requested_decision_supported"])
            self.assertEqual(payload["decision_gate"]["selected_decision"], "")

    def test_broader_rollout_rollback_decision_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-post-audit.json").write_text(
                json.dumps(post_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tool = make_plan_workspace_foldered_canonical_broader_rollout_rollback_decision_tool(root)

            payload = tool(requested_decision="defer")

            self.assertEqual(tool.__name__, "plan_workspace_foldered_canonical_broader_rollout_rollback_decision")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["broader_rollout_post_audit_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertEqual(payload["decision_gate"]["selected_decision"], "defer")
            self.assertFalse(payload["decision_gate"]["requires_separate_commit_or_rollback_executor"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((workspace / "workspace-foldered-canonical-broader-rollout-rollback-decision-plan.json").exists())

    def test_broader_rollout_decision_record_blocks_without_plan_or_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = record_workspace_foldered_canonical_broader_rollout_decision_payload(default_artifact_root=root)

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-decision-record.v1",
            )
            self.assertEqual(payload["status"], "not_ready")
            self.assertIn("rollback_decision_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("decision_required", payload["blocking_reasons"])
            self.assertFalse(payload["side_effect_policy"]["records_decision"])
            self.assertFalse(payload["side_effect_policy"]["commits_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])

    def test_broader_rollout_decision_record_dry_run_uses_ready_plan_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )

            payload = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="commit",
                reviewer="reviewer-a",
                reason="post-audit verified",
            )

            self.assertEqual(payload["status"], "ready_for_record")
            self.assertEqual(payload["summary"]["decision"], "commit")
            self.assertFalse(payload["summary"]["decision_record_written"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["records_decision"])
            self.assertIn("call_with_write_result_true_after_human_review_to_record_decision", payload["recommended_next_actions"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-decision-record.json").exists())

    def test_broader_rollout_decision_record_write_requires_reviewer_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
            )

            payload = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                write_result=True,
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("reviewer_required_to_write_decision_record", payload["blocking_reasons"])
            self.assertIn("approve_decision_record_required_to_write", payload["blocking_reasons"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-decision-record.json").exists())

    def test_broader_rollout_decision_record_can_write_reviewed_decision_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )

            payload = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                reviewer="reviewer-a",
                reason="needs rollback follow-up",
                write_result=True,
                approve_decision_record=True,
            )
            result_path = root / "workspace" / "workspace-foldered-canonical-broader-rollout-decision-record.json"
            recorded = json.loads(result_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["status"], "recorded")
            self.assertTrue(payload["summary"]["decision_record_written"])
            self.assertTrue(payload["side_effect_policy"]["artifacts_written"])
            self.assertTrue(payload["side_effect_policy"]["records_decision"])
            self.assertFalse(payload["side_effect_policy"]["commits_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])
            self.assertEqual(recorded["decision_record"]["decision"], "rollback")
            self.assertEqual(recorded["decision_record"]["reviewer"], "reviewer-a")
            self.assertTrue(recorded["decision_record"]["recorded"])
            self.assertIn("prepare_separate_reviewed_broader_rollout_rollback_executor", payload["recommended_next_actions"])

    def test_broader_rollout_decision_record_blocks_unsupported_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
            )

            payload = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="ship-it",
                reviewer="reviewer-a",
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("decision_not_supported", payload["blocking_reasons"])
            self.assertFalse(payload["side_effect_policy"]["records_decision"])

    def test_broader_rollout_decision_record_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="defer",
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-rollback-decision-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tool = make_record_workspace_foldered_canonical_broader_rollout_decision_tool(root)

            payload = tool(decision="defer", reviewer="reviewer-a")

            self.assertEqual(tool.__name__, "record_workspace_foldered_canonical_broader_rollout_decision")
            self.assertEqual(payload["status"], "ready_for_record")
            self.assertEqual(payload["rollback_decision_plan_input"]["source"], "artifact-ref")
            self.assertEqual(payload["decision_record"]["decision"], "defer")
            self.assertFalse(payload["downstream_gates"]["requires_separate_commit_or_rollback_executor"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])

    def test_execute_broader_rollout_commit_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="commit",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )

            payload = execute_workspace_foldered_canonical_broader_rollout_commit_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-commit-result.v1",
            )
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["mode"], "dry-run")
            self.assertEqual(payload["summary"]["decision"], "commit")
            self.assertEqual(payload["summary"]["manifest_entry_check_count"], 1)
            self.assertFalse(payload["summary"]["transaction_journal_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["summary"]["broader_rollout_committed"])
            self.assertFalse(payload["summary"]["broader_rollout_rolled_back"])
            self.assertFalse(payload["summary"]["canonical_paths_changed"])
            self.assertTrue(payload["side_effect_policy"]["dry_run_is_read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(payload["side_effect_policy"]["writes_result_artifact"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["commits_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["sends_cdp_commands"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])
            self.assertIn("review_commit_dry_run_then_rerun_apply_with_explicit_approval", payload["recommended_next_actions"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-commit-result.json").exists())
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-commit-journal.json").exists())

    def test_execute_broader_rollout_commit_blocks_apply_without_approval_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="commit",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )

            payload = execute_workspace_foldered_canonical_broader_rollout_commit_payload(
                default_artifact_root=root,
                mode="apply",
                approve_commit=False,
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_approve_commit_true", payload["blocking_reasons"])
            self.assertIn("apply_requires_backend_manifest_artifact_ref_not_inline_json", payload["blocking_reasons"])
            self.assertFalse(payload["summary"]["transaction_journal_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["commits_broader_rollout"])

    def test_execute_broader_rollout_commit_applies_terminal_metadata_with_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="commit",
                reviewer="reviewer-a",
                reason="post-audit accepted",
                write_result=True,
                approve_decision_record=True,
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            original_path = manifest["entries"][0]["path"]
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            payload = execute_workspace_foldered_canonical_broader_rollout_commit_payload(
                default_artifact_root=root,
                mode="apply",
                approve_commit=True,
            )

            self.assertEqual(payload["status"], "committed")
            self.assertEqual(payload["mode"], "apply")
            self.assertTrue(payload["summary"]["transaction_journal_written"])
            self.assertTrue(payload["summary"]["backend_manifest_mutated"])
            self.assertTrue(payload["summary"]["result_artifact_written"])
            self.assertTrue(payload["summary"]["broader_rollout_committed"])
            self.assertFalse(payload["summary"]["broader_rollout_rolled_back"])
            self.assertFalse(payload["summary"]["canonical_paths_changed"])
            self.assertTrue(payload["side_effect_policy"]["artifacts_written"])
            self.assertTrue(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertTrue(payload["side_effect_policy"]["writes_result_artifact"])
            self.assertTrue(payload["side_effect_policy"]["mutates_manifests"])
            self.assertTrue(payload["side_effect_policy"]["commits_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["sends_cdp_commands"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])
            self.assertTrue((workspace / "workspace-foldered-canonical-broader-rollout-commit-result.json").exists())
            self.assertTrue((workspace / "workspace-foldered-canonical-broader-rollout-commit-journal.json").exists())

            written_result = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-commit-result.json").read_text(encoding="utf-8"))
            journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-commit-journal.json").read_text(encoding="utf-8"))
            mutated_manifest = json.loads((workspace / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(written_result["summary"]["commit_transaction_id"], payload["summary"]["commit_transaction_id"])
            self.assertEqual(journal["entry_count"], 1)
            self.assertEqual(journal["entries"][0]["status"], "committed")
            self.assertEqual(journal["entries"][0]["commit_idempotency_key"], payload["summary"]["commit_idempotency_key"])
            self.assertEqual(mutated_manifest["entries"][0]["path"], original_path)
            alias = mutated_manifest["entries"][0]["metadata"]["workspace_alias"]
            self.assertTrue(alias["broader_rollout_committed"])
            self.assertFalse(alias["broader_rollout_rolled_back"])
            self.assertEqual(alias["broader_rollout_commit_transaction_id"], payload["summary"]["commit_transaction_id"])
            self.assertEqual(
                mutated_manifest["metadata"]["foldered_canonical_broader_rollout_commit_transaction_id"],
                payload["summary"]["commit_transaction_id"],
            )

    def test_execute_broader_rollout_commit_blocks_duplicate_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="commit",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            first = execute_workspace_foldered_canonical_broader_rollout_commit_payload(
                default_artifact_root=root,
                mode="apply",
                approve_commit=True,
            )

            second = execute_workspace_foldered_canonical_broader_rollout_commit_payload(
                default_artifact_root=root,
                mode="apply",
                approve_commit=True,
            )

            self.assertEqual(first["status"], "committed")
            self.assertEqual(second["status"], "blocked")
            self.assertIn("broader_rollout_commit_duplicate_idempotency_key", second["blocking_reasons"])
            self.assertTrue(second["idempotency_guard"]["duplicate_entry_found"])
            journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-commit-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(journal["entry_count"], 1)

    def test_execute_broader_rollout_commit_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="commit",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tool = make_execute_workspace_foldered_canonical_broader_rollout_commit_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "execute_workspace_foldered_canonical_broader_rollout_commit")
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["decision_record_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])

    def test_broader_rollout_rollback_preflight_blocks_without_decision_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(default_artifact_root=root)

            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-broader-rollout-rollback-preflight.v1",
            )
            self.assertEqual(payload["status"], "not_ready")
            self.assertIn("decision_record_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("decision_record_not_recorded", payload["blocking_reasons"])
            self.assertIn("decision_record_does_not_select_rollback", payload["blocking_reasons"])
            self.assertIn("backend_artifact_manifest_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertFalse(payload["summary"]["rollback_preflight_ready"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["sends_cdp_commands"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])

    def test_broader_rollout_rollback_preflight_uses_recorded_rollback_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                reviewer="reviewer-a",
                reason="rollback requested",
                write_result=True,
                approve_decision_record=True,
            )

            payload = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["decision"], "rollback")
            self.assertEqual(payload["summary"]["manifest_entry_check_count"], 1)
            self.assertEqual(payload["summary"]["ready_manifest_entry_check_count"], 1)
            self.assertTrue(payload["summary"]["all_manifest_entries_ready_for_rollback"])
            self.assertFalse(payload["summary"]["matching_commit_journal_entry_found"])
            self.assertTrue(payload["summary"]["rollback_preflight_ready"])
            self.assertTrue(payload["rollback_executor_gate"]["ready_for_rollback_executor_review"])
            self.assertTrue(payload["rollback_executor_gate"]["executor_implemented"])
            self.assertFalse(payload["rollback_executor_gate"]["rollback_apply_executed_by_this_tool"])
            self.assertEqual(payload["manifest_entry_checks"][0]["status"], "ready_for_rollback")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-rollback-preflight.json").exists())
            self.assertIn("review_rollback_preflight_before_separate_explicit_executor", payload["recommended_next_actions"])

    def test_broader_rollout_rollback_preflight_blocks_after_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            rollback_plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            rollback_decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(rollback_plan),
                decision="rollback",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            commit_plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )
            commit_decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(commit_plan),
                decision="commit",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(commit_decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            commit_result = execute_workspace_foldered_canonical_broader_rollout_commit_payload(
                default_artifact_root=root,
                mode="apply",
                approve_commit=True,
            )
            committed_manifest = json.loads((workspace / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            commit_journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-commit-journal.json").read_text(encoding="utf-8"))

            payload = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(rollback_decision),
                backend_manifest_json=json.dumps(committed_manifest),
                commit_journal_json=json.dumps(commit_journal),
            )

            self.assertEqual(commit_result["status"], "committed")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("commit_journal_contains_committed_entry_for_transaction", payload["blocking_reasons"])
            self.assertIn("manifest_entry:workspace_task_card:broader_rollout_already_committed", payload["blocking_reasons"])
            self.assertTrue(payload["commit_state_guard"]["matching_commit_journal_entry_found"])
            self.assertFalse(payload["rollback_executor_gate"]["ready_for_rollback_executor_review"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])

    def test_broader_rollout_rollback_preflight_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tool = make_review_workspace_foldered_canonical_broader_rollout_rollback_preflight_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_broader_rollout_rollback_preflight")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["decision_record_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertEqual(payload["commit_journal_input"]["source"], "artifact-ref")
            self.assertEqual(payload["commit_journal_input"]["read_status"], "missing")
            self.assertTrue(payload["rollback_executor_gate"]["ready_for_rollback_executor_review"])

    def test_execute_broader_rollout_rollback_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            preflight = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )

            payload = execute_workspace_foldered_canonical_broader_rollout_rollback_payload(
                default_artifact_root=root,
                rollback_preflight_json=json.dumps(preflight),
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-broader-rollout-rollback-result.v1")
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["summary"]["decision"], "rollback")
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertFalse(payload["summary"]["result_artifact_written"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-rollback-result.json").exists())
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-broader-rollout-rollback-journal.json").exists())
            self.assertIn("broader_rollout_rollback_dry_run_does_not_write_journal_result_or_manifest", payload["warnings"])

    def test_execute_broader_rollout_rollback_blocks_apply_without_approval_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            preflight = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )

            payload = execute_workspace_foldered_canonical_broader_rollout_rollback_payload(
                default_artifact_root=root,
                mode="apply",
                approve_rollback=False,
                rollback_preflight_json=json.dumps(preflight),
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_approve_rollback_true", payload["blocking_reasons"])
            self.assertIn("apply_requires_backend_manifest_artifact_ref_not_inline_json", payload["blocking_reasons"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_execute_broader_rollout_rollback_applies_metadata_with_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            original_path = manifest["entries"][0]["path"]
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            preflight = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-rollback-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            payload = execute_workspace_foldered_canonical_broader_rollout_rollback_payload(
                default_artifact_root=root,
                mode="apply",
                approve_rollback=True,
            )

            self.assertEqual(payload["status"], "rolled_back")
            self.assertTrue(payload["summary"]["backend_manifest_mutated"])
            self.assertTrue(payload["summary"]["result_artifact_written"])
            self.assertTrue(payload["side_effect_policy"]["artifacts_written"])
            self.assertTrue(payload["side_effect_policy"]["mutates_manifests"])
            self.assertTrue(payload["side_effect_policy"]["rolls_back_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["commits_broader_rollout"])
            self.assertFalse(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["sends_cdp_commands"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])
            self.assertTrue((workspace / "workspace-foldered-canonical-broader-rollout-rollback-result.json").exists())
            self.assertTrue((workspace / "workspace-foldered-canonical-broader-rollout-rollback-journal.json").exists())

            written_result = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-rollback-result.json").read_text(encoding="utf-8"))
            journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-rollback-journal.json").read_text(encoding="utf-8"))
            mutated_manifest = json.loads((workspace / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(written_result["summary"]["rollback_transaction_id"], payload["summary"]["rollback_transaction_id"])
            self.assertEqual(journal["entry_count"], 1)
            self.assertEqual(journal["entries"][0]["status"], "rolled_back")
            self.assertEqual(journal["entries"][0]["rollback_idempotency_key"], payload["summary"]["rollback_idempotency_key"])
            self.assertEqual(mutated_manifest["entries"][0]["path"], original_path)
            alias = mutated_manifest["entries"][0]["metadata"]["workspace_alias"]
            self.assertFalse(alias["broader_rollout_applied"])
            self.assertFalse(alias["broader_rollout_committed"])
            self.assertTrue(alias["broader_rollout_rolled_back"])
            self.assertEqual(alias["broader_rollout_rollback_transaction_id"], payload["summary"]["rollback_transaction_id"])
            self.assertEqual(
                mutated_manifest["metadata"]["foldered_canonical_broader_rollout_rollback_transaction_id"],
                payload["summary"]["rollback_transaction_id"],
            )

    def test_execute_broader_rollout_rollback_blocks_duplicate_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            preflight = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-rollback-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            first = execute_workspace_foldered_canonical_broader_rollout_rollback_payload(
                default_artifact_root=root,
                mode="apply",
                approve_rollback=True,
            )
            second = execute_workspace_foldered_canonical_broader_rollout_rollback_payload(
                default_artifact_root=root,
                mode="apply",
                approve_rollback=True,
            )

            self.assertEqual(first["status"], "rolled_back")
            self.assertEqual(second["status"], "blocked")
            self.assertIn("broader_rollout_rollback_duplicate_idempotency_key", second["blocking_reasons"])
            self.assertTrue(second["idempotency_guard"]["duplicate_entry_found"])
            journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-rollback-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(journal["entry_count"], 1)

    def test_execute_broader_rollout_rollback_blocks_committed_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            rollback_plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            rollback_decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(rollback_plan),
                decision="rollback",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            commit_plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="commit",
            )
            commit_decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(commit_plan),
                decision="commit",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(commit_decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            commit_result = execute_workspace_foldered_canonical_broader_rollout_commit_payload(
                default_artifact_root=root,
                mode="apply",
                approve_commit=True,
            )
            committed_manifest = json.loads((workspace / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            commit_journal = json.loads((workspace / "workspace-foldered-canonical-broader-rollout-commit-journal.json").read_text(encoding="utf-8"))
            rollback_preflight = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(rollback_decision),
                backend_manifest_json=json.dumps(committed_manifest),
                commit_journal_json=json.dumps(commit_journal),
            )
            (workspace / "workspace-foldered-canonical-broader-rollout-rollback-preflight.json").write_text(
                json.dumps(rollback_preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(rollback_decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            payload = execute_workspace_foldered_canonical_broader_rollout_rollback_payload(
                default_artifact_root=root,
                mode="apply",
                approve_rollback=True,
                commit_journal_json=json.dumps(commit_journal),
            )

            self.assertEqual(commit_result["status"], "committed")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("rollback_preflight_not_ready_for_review", payload["blocking_reasons"])
            self.assertIn("commit_journal_contains_committed_entry_for_transaction", payload["blocking_reasons"])
            self.assertIn("manifest_entry:workspace_task_card:broader_rollout_already_committed", payload["blocking_reasons"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["rolls_back_broader_rollout"])

    def test_execute_broader_rollout_rollback_tool_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            post_audit, manifest = self._verified_broader_rollout_post_audit_evidence(root, ["workspace_task_card"])
            plan = plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
                default_artifact_root=root,
                broader_rollout_post_audit_json=json.dumps(post_audit),
                backend_manifest_json=json.dumps(manifest),
                requested_decision="rollback",
            )
            decision = record_workspace_foldered_canonical_broader_rollout_decision_payload(
                default_artifact_root=root,
                rollback_decision_plan_json=json.dumps(plan),
                decision="rollback",
                reviewer="reviewer-a",
                write_result=True,
                approve_decision_record=True,
            )
            preflight = review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
                default_artifact_root=root,
                decision_record_json=json.dumps(decision),
                backend_manifest_json=json.dumps(manifest),
            )
            workspace = root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "workspace-foldered-canonical-broader-rollout-rollback-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "workspace-foldered-canonical-broader-rollout-decision-record.json").write_text(
                json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (workspace / "backend-artifact-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tool = make_execute_workspace_foldered_canonical_broader_rollout_rollback_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "execute_workspace_foldered_canonical_broader_rollout_rollback")
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["rollback_preflight_input"]["source"], "artifact-ref")
            self.assertEqual(payload["decision_record_input"]["source"], "artifact-ref")
            self.assertEqual(payload["backend_manifest_input"]["source"], "artifact-ref")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])

    def test_legacy_fallback_tightening_readiness_blocks_unready_consumer_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            validation_result = {
                "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation-result.v1",
                "status": "verified",
                "summary": {
                    "validation_result_count": 1,
                    "ready_validation_result_count": 1,
                    "all_promotions_observed": True,
                    "observed_canonical_path_promotion_validated": True,
                },
                "legacy_fallback_review_gate": {"requires_consumer_readiness_recheck": True},
                "blocking_reasons": [],
                "warnings": [],
            }
            readiness_score = {
                "schema_version": "reverse-deepagent.workspace-consumer-readiness-score.v1",
                "status": "blocked",
                "summary": {"overall_score": 0.4, "overall_label": "blocked"},
                "readiness": {
                    "foldered_canonical_migration_allowed": False,
                    "limited_dual_write_expansion_review_allowed": False,
                },
                "pilot_evidence": {"status": "missing", "score": 0.0},
                "blocking_reasons": ["source_path_usage_observed"],
                "warnings": [],
            }

            payload = review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_payload(
                default_artifact_root=root,
                post_apply_validation_result_json=json.dumps(validation_result),
                readiness_score_json=json.dumps(readiness_score),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("workspace_consumer_readiness_score_not_ready_for_foldered_canonical_review", payload["blocking_reasons"])
            self.assertIn("workspace_consumer_readiness_score:source_path_usage_observed", payload["blocking_reasons"])
            self.assertFalse(payload["readiness_checks"]["foldered_canonical_follow_up_allowed"])

    def test_legacy_fallback_tightening_readiness_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            validation_result = {
                "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation-result.v1",
                "status": "verified",
                "summary": {
                    "validation_result_count": 1,
                    "ready_validation_result_count": 1,
                    "all_promotions_observed": True,
                    "observed_canonical_path_promotion_validated": True,
                },
                "legacy_fallback_review_gate": {"requires_consumer_readiness_recheck": True},
                "blocking_reasons": [],
                "warnings": [],
            }
            tool = make_review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_tool(root)

            payload = tool(
                post_apply_validation_result_json=json.dumps(validation_result),
                readiness_score_json=json.dumps(self._ready_foldered_canonical_readiness_score()),
            )

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_legacy_fallback_tightening_readiness")
            self.assertEqual(
                payload["schema_version"],
                "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-readiness.v1",
            )
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])

    def test_foldered_canonical_physical_apply_preflight_blocks_without_approval_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_foldered_canonical_migration_physical_apply_preflight_payload(default_artifact_root=root)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-physical-apply-preflight.v1")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("foldered_canonical_migration_manifest_dry_run_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("foldered_canonical_migration_apply_plan_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("review_approval_ledger_unavailable_or_malformed", payload["blocking_reasons"])
            self.assertIn("review_approval_ledger_missing_matching_physical_apply_approval", payload["blocking_reasons"])
            self.assertFalse(payload["execution_gate"]["ready_for_physical_apply_executor_review"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(payload["side_effect_policy"]["writes_rollback_checkpoint"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_foldered_canonical_physical_apply_preflight_uses_ready_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card", "workspace_runtime_context"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
                transaction_id="tx-foldered-physical",
                idempotency_key="idem-foldered-physical",
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )
            approval_ledger = self._approval_ledger_for_physical_apply(dry_run)

            payload = review_workspace_foldered_canonical_migration_physical_apply_preflight_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                review_approval_ledger_json=json.dumps(approval_ledger),
            )

            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["planned_apply_step_count"], 2)
            self.assertTrue(payload["summary"]["matching_review_approval_found"])
            self.assertFalse(payload["summary"]["rollback_checkpoint_provided"])
            self.assertTrue(payload["summary"]["rollback_checkpoint_required_before_manifest_mutation"])
            self.assertTrue(payload["summary"]["transaction_journal_required"])
            self.assertTrue(payload["summary"]["idempotency_guard_required"])
            self.assertTrue(payload["summary"]["post_apply_validation_required"])
            self.assertFalse(payload["summary"]["physical_apply_executed_by_this_tool"])
            self.assertTrue(payload["digest_guard"]["digest_match"])
            self.assertTrue(payload["review_approval_gate"]["approved"])
            self.assertTrue(payload["review_approval_gate"]["digest_matches_expected"])
            self.assertTrue(payload["rollback_checkpoint_gate"]["required_before_manifest_mutation"])
            self.assertTrue(payload["rollback_checkpoint_gate"]["must_be_written_by_physical_apply_executor_before_manifest_mutation"])
            self.assertTrue(payload["transaction_journal_plan"]["required"])
            self.assertFalse(payload["transaction_journal_plan"]["writes_journal_in_this_tool"])
            self.assertTrue(payload["idempotency_guard"]["required"])
            self.assertEqual(payload["idempotency_guard"]["idempotency_key"], "idem-foldered-physical")
            self.assertTrue(payload["post_apply_validation_requirement"]["required_after_apply"])
            self.assertFalse(payload["post_apply_validation_requirement"]["runs_validation_in_this_tool"])
            self.assertEqual(payload["executor_inputs"]["apply_step_count"], 2)
            self.assertTrue(payload["execution_gate"]["ready_for_physical_apply_executor_review"])
            self.assertFalse(payload["execution_gate"]["allows_automatic_execution"])
            self.assertFalse(payload["execution_gate"]["allows_journal_write_in_this_tool"])
            self.assertFalse(payload["execution_gate"]["allows_manifest_mutation_in_this_tool"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(payload["side_effect_policy"]["writes_rollback_checkpoint"])
            self.assertFalse(payload["side_effect_policy"]["mutates_manifests"])

    def test_foldered_canonical_physical_apply_preflight_blocks_approval_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )
            approval_ledger = self._approval_ledger_for_physical_apply(dry_run, digest_override="0" * 64)

            payload = review_workspace_foldered_canonical_migration_physical_apply_preflight_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                review_approval_ledger_json=json.dumps(approval_ledger),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("review_approval_ledger_does_not_approve_physical_apply", payload["blocking_reasons"])
            self.assertFalse(payload["review_approval_gate"]["approved"])
            self.assertFalse(payload["review_approval_gate"]["digest_matches_expected"])
            self.assertFalse(payload["execution_gate"]["ready_for_physical_apply_executor_review"])

    def test_foldered_canonical_physical_apply_preflight_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            preflight = self._ready_foldered_canonical_migration_preflight(root, ["workspace_task_card"])
            apply_plan = plan_workspace_foldered_canonical_migration_apply_payload(
                default_artifact_root=root,
                migration_preflight_json=json.dumps(preflight),
            )
            approval_plan = plan_workspace_foldered_canonical_migration_approval_payload(
                default_artifact_root=root,
                migration_apply_plan_json=json.dumps(apply_plan),
            )
            dry_run = review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
                default_artifact_root=root,
                migration_approval_plan_json=json.dumps(approval_plan),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(self._backend_manifest_for_apply_plan(apply_plan)),
            )
            tool = make_review_workspace_foldered_canonical_migration_physical_apply_preflight_tool(root)

            payload = tool(
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                review_approval_ledger_json=json.dumps(self._approval_ledger_for_physical_apply(dry_run)),
            )

            self.assertEqual(tool.__name__, "review_workspace_foldered_canonical_migration_physical_apply_preflight")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-physical-apply-preflight.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_execute_foldered_canonical_physical_apply_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            apply_plan, dry_run, physical_preflight, backend_manifest = self._ready_physical_apply_evidence(root, ["workspace_task_card"])

            payload = execute_workspace_foldered_canonical_physical_apply_payload(
                default_artifact_root=root,
                physical_apply_preflight_json=json.dumps(physical_preflight),
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(backend_manifest),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-physical-apply-result.v1")
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["summary"]["planned_manifest_change_count"], 1)
            self.assertFalse(payload["summary"]["rollback_checkpoint_written"])
            self.assertFalse(payload["summary"]["transaction_journal_written"])
            self.assertFalse(payload["summary"]["backend_manifest_mutated"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["writes_rollback_checkpoint"])
            self.assertFalse(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-physical-apply-result.json").exists())
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-physical-apply-journal.json").exists())

    def test_execute_foldered_canonical_physical_apply_blocks_apply_without_approval_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            apply_plan, dry_run, physical_preflight, backend_manifest = self._ready_physical_apply_evidence(root, ["workspace_task_card"])
            self._write_physical_apply_evidence_artifacts(
                root,
                apply_plan=apply_plan,
                dry_run=dry_run,
                physical_preflight=physical_preflight,
                backend_manifest=backend_manifest,
            )

            payload = execute_workspace_foldered_canonical_physical_apply_payload(
                default_artifact_root=root,
                mode="apply",
                approve_physical_apply=False,
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_approve_physical_apply_true", payload["blocking_reasons"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-rollback-checkpoint.json").exists())
            self.assertFalse((root / "workspace" / "workspace-foldered-canonical-migration-physical-apply-journal.json").exists())

    def test_execute_foldered_canonical_physical_apply_promotes_backend_manifest_with_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            apply_plan, dry_run, physical_preflight, backend_manifest = self._ready_physical_apply_evidence(root, ["workspace_task_card", "workspace_runtime_context"])
            self._write_physical_apply_evidence_artifacts(
                root,
                apply_plan=apply_plan,
                dry_run=dry_run,
                physical_preflight=physical_preflight,
                backend_manifest=backend_manifest,
            )

            payload = execute_workspace_foldered_canonical_physical_apply_payload(
                default_artifact_root=root,
                mode="apply",
                approve_physical_apply=True,
            )

            self.assertEqual(payload["status"], "applied")
            self.assertEqual(payload["summary"]["applied_manifest_change_count"], 2)
            self.assertTrue(payload["summary"]["rollback_checkpoint_written"])
            self.assertTrue(payload["summary"]["transaction_journal_written"])
            self.assertTrue(payload["summary"]["backend_manifest_mutated"])
            self.assertTrue(payload["summary"]["result_artifact_written"])
            self.assertTrue(payload["side_effect_policy"]["artifacts_written"])
            self.assertTrue(payload["side_effect_policy"]["writes_rollback_checkpoint"])
            self.assertTrue(payload["side_effect_policy"]["writes_transaction_journal"])
            self.assertTrue(payload["side_effect_policy"]["mutates_manifests"])
            self.assertTrue(payload["side_effect_policy"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_policy"]["moves_files"])
            self.assertFalse(payload["side_effect_policy"]["tightens_legacy_fallback"])
            rollback_path = root / "workspace" / "workspace-foldered-canonical-migration-rollback-checkpoint.json"
            journal_path = root / "workspace" / "workspace-foldered-canonical-migration-physical-apply-journal.json"
            result_path = root / "workspace" / "workspace-foldered-canonical-migration-physical-apply-result.json"
            self.assertTrue(rollback_path.exists())
            self.assertTrue(journal_path.exists())
            self.assertTrue(result_path.exists())
            mutated = json.loads((root / "workspace" / "backend-artifact-manifest.json").read_text(encoding="utf-8"))
            for entry, step in zip(mutated["entries"], apply_plan["apply_plan"]["planned_steps"]):
                self.assertEqual(entry["path"], step["future_canonical_path"])
                alias = entry["metadata"]["workspace_alias"]
                self.assertEqual(alias["legacy_fallback_path"], step["current_canonical_path"])
                self.assertFalse(alias["canonical_path_remains_authoritative"])
                self.assertTrue(alias["legacy_fallback_preserved"])
                self.assertFalse(alias["legacy_fallback_tightened"])
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(journal["entry_count"], 1)
            self.assertEqual(journal["entries"][0]["status"], "applied")
            validation = review_workspace_foldered_canonical_migration_post_apply_validation_payload(
                default_artifact_root=root,
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                post_apply_backend_manifest_json=json.dumps(mutated),
            )
            self.assertEqual(validation["status"], "ready_for_review")

    def test_execute_foldered_canonical_physical_apply_blocks_duplicate_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            apply_plan, dry_run, physical_preflight, backend_manifest = self._ready_physical_apply_evidence(root, ["workspace_task_card"])
            self._write_physical_apply_evidence_artifacts(
                root,
                apply_plan=apply_plan,
                dry_run=dry_run,
                physical_preflight=physical_preflight,
                backend_manifest=backend_manifest,
            )
            first = execute_workspace_foldered_canonical_physical_apply_payload(
                default_artifact_root=root,
                mode="apply",
                approve_physical_apply=True,
            )
            self.assertEqual(first["status"], "applied")

            duplicate = execute_workspace_foldered_canonical_physical_apply_payload(
                default_artifact_root=root,
                mode="apply",
                approve_physical_apply=True,
            )

            self.assertEqual(duplicate["status"], "blocked")
            self.assertIn("physical_apply_duplicate_idempotency_key", duplicate["blocking_reasons"])
            self.assertTrue(duplicate["idempotency_guard"]["duplicate_entry_found"])
            journal = json.loads((root / "workspace" / "workspace-foldered-canonical-migration-physical-apply-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(journal["entry_count"], 1)

    def test_execute_foldered_canonical_physical_apply_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            apply_plan, dry_run, physical_preflight, backend_manifest = self._ready_physical_apply_evidence(root, ["workspace_task_card"])
            tool = make_execute_workspace_foldered_canonical_physical_apply_tool(root)

            payload = tool(
                physical_apply_preflight_json=json.dumps(physical_preflight),
                migration_manifest_dry_run_json=json.dumps(dry_run),
                migration_apply_plan_json=json.dumps(apply_plan),
                backend_manifest_json=json.dumps(backend_manifest),
            )

            self.assertEqual(tool.__name__, "execute_workspace_foldered_canonical_physical_apply")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-foldered-canonical-migration-physical-apply-result.v1")
            self.assertEqual(payload["status"], "planned")
            self.assertTrue(payload["side_effect_policy"]["dry_run_is_read_only"])

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

    def test_workspace_dual_write_pilot_result_reports_not_run_without_observed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = record_workspace_dual_write_pilot_result_payload(default_artifact_root=root)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-result.v1")
            self.assertEqual(payload["status"], "not_run")
            self.assertIn("workspace_dual_write_plan_not_observed", payload["blocking_reasons"])
            self.assertFalse(payload["result_artifact"]["written"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertTrue(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse((root / "workspace" / "workspace-dual-write-pilot-result.json").exists())

    def test_workspace_dual_write_pilot_result_verifies_matching_legacy_and_future_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = plan_workspace_dual_write_pilot_payload(
                default_artifact_root=root,
                artifact_keys_json=json.dumps(["workspace_task_card"]),
            )
            legacy = root / "workspace" / "task-card.json"
            future = root / "workspace" / "recon" / "task-card.json"
            legacy.parent.mkdir(parents=True)
            future.parent.mkdir(parents=True)
            payload_text = json.dumps({"task": "demo", "n": 1}, sort_keys=True) + "\n"
            legacy.write_text(payload_text, encoding="utf-8")
            future.write_text(payload_text, encoding="utf-8")
            observed = {
                "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
                "status": "applied",
                "records": [
                    {
                        "artifact_key": "workspace_task_card",
                        "canonical_path": "workspace/task-card.json",
                        "future_path": "/workspace/recon/task-card.json",
                        "write_paths": [str(legacy), str(future)],
                        "canonical_path_remains_authoritative": True,
                    }
                ],
            }
            (root / "workspace" / "workspace-dual-write-plan.json").write_text(json.dumps(observed), encoding="utf-8")

            result = record_workspace_dual_write_pilot_result_payload(
                default_artifact_root=root,
                pilot_plan_json=json.dumps(plan),
            )

            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["summary"]["planned_candidate_count"], 1)
            self.assertEqual(result["summary"]["verified_candidate_count"], 1)
            self.assertEqual(result["summary"]["out_of_scope_observed_count"], 0)
            candidate = result["candidate_results"][0]
            self.assertEqual(candidate["status"], "verified_dual_written")
            self.assertTrue(candidate["digest_match"])
            self.assertTrue(candidate["legacy_file"]["exists"])
            self.assertTrue(candidate["future_file"]["exists"])
            self.assertEqual(candidate["legacy_file"]["sha256"], candidate["future_file"]["sha256"])
            self.assertTrue(result["side_effect_policy"]["read_only"])
            self.assertFalse(result["side_effect_policy"]["artifacts_written"])

    def test_workspace_dual_write_pilot_result_ignores_scoped_legacy_only_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = plan_workspace_dual_write_pilot_payload(
                default_artifact_root=root,
                artifact_keys_json=json.dumps(["workspace_task_card"]),
            )
            legacy_task = root / "workspace" / "task-card.json"
            future_task = root / "workspace" / "recon" / "task-card.json"
            legacy_route = root / "workspace" / "route-decision.json"
            legacy_task.parent.mkdir(parents=True)
            future_task.parent.mkdir(parents=True)
            legacy_task.write_text('{"task": "demo"}\n', encoding="utf-8")
            future_task.write_text('{"task": "demo"}\n', encoding="utf-8")
            legacy_route.write_text('{"route": "legacy-only"}\n', encoding="utf-8")
            observed = {
                "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
                "status": "applied",
                "mode": "scoped-opt-in-dual-write",
                "dual_write_scope_enabled": True,
                "dual_write_scope_artifact_keys": ["workspace_task_card"],
                "records": [
                    {
                        "artifact_key": "workspace_task_card",
                        "canonical_path": "workspace/task-card.json",
                        "future_path": "/workspace/recon/task-card.json",
                        "write_paths": [str(legacy_task), str(future_task)],
                        "dual_write_enabled": True,
                    },
                    {
                        "artifact_key": "workspace_route",
                        "canonical_path": "workspace/route-decision.json",
                        "future_path": "/workspace/recon/route-decision.json",
                        "write_paths": [str(legacy_route)],
                        "dual_write_enabled": False,
                        "dual_write_scope_enabled": True,
                        "dual_write_in_scope": False,
                    },
                ],
            }

            result = record_workspace_dual_write_pilot_result_payload(
                default_artifact_root=root,
                pilot_plan_json=json.dumps(plan),
                workspace_dual_write_plan_json=json.dumps(observed),
            )

            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["summary"]["out_of_scope_observed_count"], 0)
            self.assertEqual(result["out_of_scope_observed_artifacts"], [])
            self.assertNotIn("observed_dual_write_records_outside_pilot_plan", result["warnings"])

    def test_workspace_dual_write_pilot_result_can_write_audit_artifact_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            plan = plan_workspace_dual_write_pilot_payload(
                default_artifact_root=root,
                artifact_keys_json=json.dumps(["workspace_task_card"]),
            )
            legacy = root / "workspace" / "task-card.json"
            future = root / "workspace" / "recon" / "task-card.json"
            legacy.parent.mkdir(parents=True)
            future.parent.mkdir(parents=True)
            legacy.write_text('{"ok": true}\n', encoding="utf-8")
            future.write_text('{"ok": true}\n', encoding="utf-8")
            observed = {
                "status": "applied",
                "records": [
                    {
                        "artifact_key": "workspace_task_card",
                        "canonical_path": "workspace/task-card.json",
                        "future_path": "/workspace/recon/task-card.json",
                        "write_paths": [str(legacy), str(future)],
                    }
                ],
            }

            result = record_workspace_dual_write_pilot_result_payload(
                default_artifact_root=root,
                pilot_plan_json=json.dumps(plan),
                workspace_dual_write_plan_json=json.dumps(observed),
                write_result=True,
            )

            result_path = root / "workspace" / "workspace-dual-write-pilot-result.json"
            self.assertEqual(result["status"], "verified")
            self.assertTrue(result["result_artifact"]["written"])
            self.assertEqual(result["result_artifact"]["path"], str(result_path))
            self.assertTrue(result_path.exists())
            written = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-result.v1")
            self.assertEqual(written["status"], "verified")
            self.assertFalse(written["side_effect_policy"]["read_only"])
            self.assertTrue(written["side_effect_policy"]["artifacts_written"])
            self.assertFalse(written["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(written["side_effect_policy"]["changes_canonical_paths"])

    def test_workspace_dual_write_pilot_result_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            tool = make_record_workspace_dual_write_pilot_result_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "record_workspace_dual_write_pilot_result")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-result.v1")
            self.assertEqual(payload["status"], "not_run")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])

    def test_workspace_dual_write_pilot_workflow_returns_review_plan_without_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = review_workspace_dual_write_pilot_workflow_payload(
                default_artifact_root=root,
                artifact_keys_json=json.dumps(["workspace_task_card"]),
            )

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-workflow.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["pilot_plan_status"], "ready_for_review")
            self.assertEqual(payload["summary"]["pilot_result_status"], "not_run")
            self.assertEqual(payload["summary"]["selected_artifact_count"], 1)
            self.assertTrue(payload["summary"]["review_required"])
            self.assertTrue(payload["summary"]["mobile_full_runtime_chains_deferred"])
            self.assertEqual(payload["pilot_plan"]["candidate_artifacts"][0]["artifact_key"], "workspace_task_card")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertTrue(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["runs_pipeline"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse((root / "workspace" / "workspace-dual-write-pilot-result.json").exists())
            self.assertTrue(payload["review_workflow"]["requires_explicit_pipeline_run"])
            self.assertTrue(payload["review_workflow"]["requires_review_before_expansion"])
            self.assertIn("workspace_task_card", payload["review_workflow"]["selected_artifact_keys"])

    def test_workspace_dual_write_pilot_workflow_verifies_observed_scoped_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            legacy = root / "workspace" / "task-card.json"
            future = root / "workspace" / "recon" / "task-card.json"
            legacy.parent.mkdir(parents=True)
            future.parent.mkdir(parents=True)
            payload_text = json.dumps({"task": "demo", "n": 1}, sort_keys=True) + "\n"
            legacy.write_text(payload_text, encoding="utf-8")
            future.write_text(payload_text, encoding="utf-8")
            observed = {
                "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
                "status": "applied",
                "mode": "scoped-opt-in-dual-write",
                "records": [
                    {
                        "artifact_key": "workspace_task_card",
                        "canonical_path": "workspace/task-card.json",
                        "future_path": "/workspace/recon/task-card.json",
                        "write_paths": [str(legacy), str(future)],
                        "dual_write_enabled": True,
                    }
                ],
            }

            result = review_workspace_dual_write_pilot_workflow_payload(
                default_artifact_root=root,
                artifact_keys_json=json.dumps(["workspace_task_card"]),
                workspace_dual_write_plan_json=json.dumps(observed),
            )

            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["summary"]["pilot_result_status"], "verified")
            self.assertEqual(result["pilot_result"]["summary"]["verified_candidate_count"], 1)
            self.assertEqual(result["pilot_result"]["candidate_results"][0]["status"], "verified_dual_written")
            self.assertTrue(result["side_effect_policy"]["read_only"])
            self.assertFalse(result["side_effect_policy"]["artifacts_written"])

    def test_workspace_dual_write_pilot_workflow_blocks_high_risk_scope_before_pipeline_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            result = review_workspace_dual_write_pilot_workflow_payload(
                default_artifact_root=root,
                artifact_keys_json=json.dumps(["workspace_delivery_receipt"]),
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn(
                "pilot_plan:high_risk_requested_artifacts_require_separate_review",
                result["blocking_reasons"],
            )
            self.assertFalse(result["review_workflow"]["requires_explicit_pipeline_run"])
            self.assertEqual(result["review_workflow"]["recommended_commands"][0]["step"], "resolve_workflow_blockers")
            self.assertFalse(result["side_effect_policy"]["runs_pipeline"])

    def test_workspace_dual_write_pilot_workflow_write_result_only_writes_audit_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            legacy = root / "workspace" / "task-card.json"
            future = root / "workspace" / "recon" / "task-card.json"
            legacy.parent.mkdir(parents=True)
            future.parent.mkdir(parents=True)
            legacy.write_text('{"ok": true}\n', encoding="utf-8")
            future.write_text('{"ok": true}\n', encoding="utf-8")
            observed = {
                "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
                "status": "applied",
                "records": [
                    {
                        "artifact_key": "workspace_task_card",
                        "canonical_path": "workspace/task-card.json",
                        "future_path": "/workspace/recon/task-card.json",
                        "write_paths": [str(legacy), str(future)],
                        "dual_write_enabled": True,
                    }
                ],
            }

            result = review_workspace_dual_write_pilot_workflow_payload(
                default_artifact_root=root,
                artifact_keys_json=json.dumps(["workspace_task_card"]),
                workspace_dual_write_plan_json=json.dumps(observed),
                write_result=True,
            )

            result_path = root / "workspace" / "workspace-dual-write-pilot-result.json"
            self.assertEqual(result["status"], "verified")
            self.assertFalse(result["side_effect_policy"]["read_only"])
            self.assertTrue(result["side_effect_policy"]["artifacts_written"])
            self.assertFalse(result["side_effect_policy"]["runs_pipeline"])
            self.assertFalse(result["side_effect_policy"]["changes_canonical_paths"])
            self.assertTrue(result_path.exists())
            written = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-result.v1")
            self.assertEqual(written["status"], "verified")
            self.assertFalse((root / "workspace" / "recon" / "workspace-dual-write-pilot-result.json").exists())

    def test_workspace_dual_write_pilot_workflow_tool_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            tool = make_review_workspace_dual_write_pilot_workflow_tool(root)

            payload = tool(artifact_keys_json=json.dumps(["workspace_task_card"]))

            self.assertEqual(tool.__name__, "review_workspace_dual_write_pilot_workflow")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-workflow.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])


if __name__ == "__main__":
    unittest.main()
