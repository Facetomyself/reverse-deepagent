import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.tools.workspace_dual_write_pilot import (
    make_plan_workspace_dual_write_pilot_tool,
    make_record_workspace_dual_write_pilot_result_tool,
    make_review_workspace_dual_write_pilot_workflow_tool,
    plan_workspace_dual_write_pilot_payload,
    record_workspace_dual_write_pilot_result_payload,
    review_workspace_dual_write_pilot_workflow_payload,
)


class WorkspaceDualWritePilotTests(unittest.TestCase):
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
