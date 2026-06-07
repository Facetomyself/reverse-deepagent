import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.agent import build_reverse_agent
from reverse_deepagent.schemas import ArtifactKind, ArtifactRef, ExecutionStatus, FinalResult, RebuildResult, ReverseMode, ReverseStage, TaskCard
from reverse_deepagent.subagents.rebuild import REBUILD_SUBAGENT_DESCRIPTION, REBUILD_SUBAGENT_NAME, build_rebuild_subagent, load_rebuild_prompt
from reverse_deepagent.tools.rebuild_tools import make_build_rebuild_delivery_tool, make_review_rebuild_artifacts_tool


class ToolFriendlyFakeModel:
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


class RebuildSubagentTests(unittest.TestCase):
    def test_review_rebuild_artifacts_blocks_risk_review_hint(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={
                "ready": True,
                "entrypoint": "buildSign",
                "candidate_id": "candidate-1",
                "algorithm_strategy": {"id": "dynamic_secret_triage"},
                "pure_extraction": {"pure_extractable": False, "context_aware_extractable": False},
                "review_hints": [
                    {
                        "severity": "risk",
                        "category": "strategy",
                        "code": "dynamic_secret_required",
                        "message": "Runtime secret is required.",
                        "evidence": ["secret source unknown"],
                    }
                ],
            },
            generated_files={"rebuild_plan": "/tmp/rebuild-plan.json", "readme": "/tmp/README.md"},
            artifacts=[ArtifactRef(path="/tmp/rebuild-plan.json", kind=ArtifactKind.JSON, description="plan")],
            next_action="manual_port_or_expand_source_context",
        )

        result = make_review_rebuild_artifacts_tool()(rebuild.model_dump_json())

        self.assertEqual(result["status"], "block")
        self.assertIn("risk_review_hints_block_rebuild_delivery", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_rebuild_risk_hints_before_delivery")
        self.assertEqual(result["summary"]["risk_hint_codes"], ["dynamic_secret_required"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["artifacts_written"])
        self.assertFalse(result["side_effect_policy"]["replay_executed"])
        self.assertFalse(result["side_effect_policy"]["delivery_executed"])

    def test_review_rebuild_artifacts_passes_ready_bundle_with_generated_files(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={
                "ready": True,
                "entrypoint": "buildSign",
                "candidate_id": "candidate-1",
                "algorithm_strategy": {"id": "sig_keyword_timestamp_template"},
                "pure_extraction": {"pure_extractable": True},
                "outputs": {"sign_rebuild": "artifacts/rebuild/sign_rebuild.py"},
                "review_hints": [],
            },
            generated_files={"rebuild_plan": "/tmp/rebuild-plan.json", "sign_rebuild": "/tmp/sign_rebuild.py"},
            artifacts=[ArtifactRef(path="/tmp/rebuild-plan.json", kind=ArtifactKind.JSON, description="plan")],
            next_action="run_replay_demo_or_integrate_scrapy",
        )

        result = make_review_rebuild_artifacts_tool()(rebuild.model_dump_json())

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["next_action"], "run_replay_demo_or_integrate_scrapy")
        self.assertTrue(result["summary"]["ready"])
        self.assertEqual(result["summary"]["generated_file_count"], 2)
        self.assertEqual(result["summary"]["algorithm_strategy_id"], "sig_keyword_timestamp_template")

    def test_review_rebuild_artifacts_warns_when_plan_not_ready(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.PARTIAL,
            rebuild_plan={"ready": False, "review_hints": []},
            next_action="manual_port_or_expand_source_context",
        )

        result = make_review_rebuild_artifacts_tool()(rebuild.model_dump_json())

        self.assertEqual(result["status"], "warn")
        self.assertIn("rebuild_plan_not_ready", result["warnings"])
        self.assertEqual(result["next_action"], "manual_port_or_expand_source_context")


    def test_review_rebuild_artifacts_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            workspace = artifact_root / "workspace"
            workspace.mkdir(parents=True)
            rebuild = RebuildResult(
                status=ExecutionStatus.SUCCESS,
                rebuild_plan={"ready": True, "review_hints": []},
                generated_files={"rebuild_plan": "/tmp/rebuild-plan.json"},
                artifacts=[ArtifactRef(path="/tmp/rebuild-plan.json", kind=ArtifactKind.JSON, description="plan")],
                next_action="run_replay_demo_or_integrate_scrapy",
            )
            plan = {"ready": True, "entrypoint": "buildSign", "review_hints": []}
            (workspace / "rebuild-result.json").write_text(rebuild.model_dump_json(), encoding="utf-8")
            (workspace / "rebuild-plan.json").write_text(json.dumps(plan), encoding="utf-8")

            result = make_review_rebuild_artifacts_tool(artifact_root)(
                rebuild_result_artifact_ref="workspace/rebuild-result.json",
                rebuild_plan_artifact_ref="workspace_rebuild_plan",
            )

            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["summary"]["entrypoint"], "buildSign")
            self.assertEqual(result["artifact_input"]["rebuild_plan"]["artifact_ref"], "workspace_rebuild_plan")
            self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_build_rebuild_delivery_reads_task_and_final_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            workspace = artifact_root / "workspace"
            workspace.mkdir(parents=True)
            task_card = TaskCard(
                target_url_or_file="https://example.test/app",
                target_param_or_api="sign",
                goal="生成 rebuild",
                boundaries="unit test",
            )
            final_result = FinalResult(
                task_card=task_card,
                mode=ReverseMode.FIND_ENTRY,
                stage=ReverseStage.FINAL,
                status=ExecutionStatus.PARTIAL,
                next_action="manual_port_or_expand_source_context",
            )
            (workspace / "task-card.json").write_text(task_card.model_dump_json(), encoding="utf-8")
            (workspace / "final-result.json").write_text(final_result.model_dump_json(), encoding="utf-8")

            result = make_build_rebuild_delivery_tool(artifact_root)(
                task_card_artifact_ref="workspace_task_card",
                final_result_artifact_ref="virtual://workspace/delivery/final-result.json",
            )

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["artifact_input"]["task_card"]["artifact_ref"], "workspace_task_card")
            self.assertEqual(result["artifact_input"]["final_result"]["resolver_metrics"]["artifact_ref_kind"], "virtual-uri")
            self.assertTrue((workspace / "rebuild-plan.json").exists())
            self.assertTrue((artifact_root / "rebuild" / "README.md").exists())

    def test_build_rebuild_delivery_rejects_ambiguous_json_and_artifact_ref(self) -> None:
        task_card = TaskCard(
            target_url_or_file="https://example.test/app",
            target_param_or_api="sign",
            goal="生成 rebuild",
            boundaries="unit test",
        )

        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            make_build_rebuild_delivery_tool("artifacts")(
                task_card_json=task_card.model_dump_json(),
                task_card_artifact_ref="workspace_task_card",
                final_result_json="{}",
            )

    def test_build_rebuild_subagent_exposes_build_and_review_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subagent = build_rebuild_subagent(Path(tmp) / "artifacts")

        self.assertEqual(subagent["name"], REBUILD_SUBAGENT_NAME)
        self.assertEqual(subagent["description"], REBUILD_SUBAGENT_DESCRIPTION)
        self.assertIn("Rebuild Subagent", subagent["system_prompt"])
        self.assertEqual({tool.__name__ for tool in subagent["tools"]}, {"read_workspace_artifact", "build_rebuild_delivery", "review_rebuild_artifacts"})

    def test_prompt_loader_supports_custom_path(self) -> None:
        path = Path(__file__).resolve().parents[1] / "src/reverse_deepagent/prompts/rebuild.txt"
        self.assertIn("Rebuild Subagent", load_rebuild_prompt(path))

    def test_default_agent_includes_rebuild_between_review_and_delivery(self) -> None:
        captured = {}

        def fake_create_deep_agent(**kwargs):
            captured.update(kwargs)
            return {"captured": kwargs}

        import reverse_deepagent.agent as agent_module

        original = agent_module.create_deep_agent
        try:
            agent_module.create_deep_agent = fake_create_deep_agent
            build_reverse_agent(model=ToolFriendlyFakeModel())
        finally:
            agent_module.create_deep_agent = original

        names = [item["name"] for item in captured["subagents"]]
        self.assertIn("rebuild", names)
        self.assertIn("delivery", names)
        self.assertLess(names.index("review"), names.index("rebuild"))
        self.assertLess(names.index("rebuild"), names.index("delivery"))
        tool_names = {tool.__name__ for tool in captured["tools"]}
        self.assertIn("read_workspace_artifact", tool_names)
        self.assertIn("audit_workspace_artifact_consumers", tool_names)
        self.assertIn("assess_workspace_migration_readiness", tool_names)
        self.assertIn("assess_workspace_consumer_readiness_score", tool_names)
        self.assertIn("plan_workspace_dual_write_expansion", tool_names)
        self.assertIn("review_workspace_dual_write_expansion_workflow", tool_names)
        self.assertIn("record_workspace_dual_write_expansion_result", tool_names)
        self.assertIn("plan_workspace_foldered_canonical_migration_pilot", tool_names)
        self.assertIn("review_workspace_foldered_canonical_migration_preflight", tool_names)
        self.assertIn("plan_workspace_foldered_canonical_migration_apply", tool_names)
        self.assertIn("plan_workspace_foldered_canonical_migration_approval", tool_names)
        self.assertIn("review_workspace_foldered_canonical_migration_manifest_dry_run", tool_names)
        self.assertIn("review_workspace_foldered_canonical_migration_post_apply_validation", tool_names)
        self.assertIn("review_workspace_foldered_canonical_migration_physical_apply_preflight", tool_names)
        self.assertIn("plan_workspace_dual_write_pilot", tool_names)
        self.assertIn("review_workspace_dual_write_pilot_workflow", tool_names)
        self.assertIn("record_workspace_dual_write_pilot_result", tool_names)
        self.assertIn("build_rebuild_delivery", tool_names)


if __name__ == "__main__":
    unittest.main()
