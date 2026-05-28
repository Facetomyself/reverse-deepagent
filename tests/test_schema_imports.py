import unittest

from reverse_deepagent.schemas import (
    ConfidenceLevel,
    ExecutionStatus,
    FinalResult,
    KeyFindings,
    RebuildResult,
    ReconResult,
    ReverseMode,
    ReverseStage,
    RouterResult,
    TaskCard,
)
from reverse_deepagent.runtime import RuntimeBackendCapabilities


class SchemaImportTests(unittest.TestCase):
    def test_router_and_final_result_models_can_be_instantiated(self) -> None:
        task_card = TaskCard(
            target_url_or_file="https://example.com/search",
            target_param_or_api="x-sign",
            goal="找到 x-sign 的生成入口并给出下一步建议",
            boundaries="不登录，不做破坏性操作",
            sample_request="POST /api/search",
            protection_hints=["debugger", "webpack"],
        )

        route = RouterResult(
            selected_mode=ReverseMode.FULL_WORKFLOW,
            selected_playbook="references/playbooks/full-workflow.md",
            initial_stage=ReverseStage.RECON,
            reasoning=["用户意图跨多个阶段", "目标是定位 sign 生成入口"],
            confidence=ConfidenceLevel.HIGH,
            next_action="delegate_to_web_recon",
        )

        recon = ReconResult(
            status=ExecutionStatus.PARTIAL,
            stage=ReverseStage.RECON,
            key_findings=KeyFindings(
                facts=["已捕获目标请求"],
                inferences=["sign 可能由 webpack bundle 中某模块生成"],
                unknowns=["尚未确认具体函数位置"],
            ),
            next_action="move_to_source_analysis",
            confidence=ConfidenceLevel.MEDIUM,
        )

        final_result = FinalResult(
            task_card=task_card,
            mode=route.selected_mode,
            stage=recon.stage,
            status=recon.status,
            key_findings=recon.key_findings,
            evidence=recon.evidence,
            artifacts=recon.artifacts,
            next_action=recon.next_action,
            confidence=recon.confidence,
        )

        self.assertEqual(final_result.task_card.target_param_or_api, "x-sign")
        self.assertEqual(final_result.key_findings.facts, ["已捕获目标请求"])
        self.assertEqual(final_result.status, ExecutionStatus.PARTIAL)

        rebuild_result = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={"ready": True},
            generated_files={"sign_rebuild": "/tmp/sign_rebuild.py"},
            next_action="run_replay_demo_or_integrate_scrapy",
        )
        self.assertTrue(rebuild_result.rebuild_plan["ready"])

        capabilities = RuntimeBackendCapabilities(
            backend_id="mock",
            display_name="Mock Runtime",
            transport="in-process",
            target_platforms=["web"],
            supports_web_recon=True,
        )
        serialized = capabilities.model_dump(mode="json")
        self.assertEqual(serialized["backend_id"], "mock")
        self.assertTrue(serialized["supports_web_recon"])


if __name__ == "__main__":
    unittest.main()
