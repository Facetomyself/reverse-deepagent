import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.tools.artifact_tools import (
    assess_workspace_consumer_readiness_score_payload,
    assess_workspace_migration_readiness_payload,
    audit_workspace_artifact_consumers_payload,
    make_assess_workspace_consumer_readiness_score_tool,
    make_assess_workspace_migration_readiness_tool,
    make_audit_workspace_artifact_consumers_tool,
    make_plan_workspace_dual_write_expansion_tool,
    make_plan_workspace_dual_write_pilot_tool,
    make_read_workspace_artifact_tool,
    make_record_workspace_dual_write_expansion_result_tool,
    make_record_workspace_dual_write_pilot_result_tool,
    make_review_workspace_dual_write_expansion_workflow_tool,
    make_review_workspace_dual_write_pilot_workflow_tool,
    plan_workspace_dual_write_pilot_payload,
    plan_workspace_dual_write_expansion_payload,
    record_workspace_dual_write_expansion_result_payload,
    record_workspace_dual_write_pilot_result_payload,
    review_workspace_dual_write_expansion_workflow_payload,
    review_workspace_dual_write_pilot_workflow_payload,
    summarize_workspace_artifact_read,
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
