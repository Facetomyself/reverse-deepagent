import unittest

from reverse_deepagent.schemas import (
    ConfidenceLevel,
    ExecutionStatus,
    EvidenceItem,
    EvidenceKind,
    FinalResult,
    KeyFindings,
    RebuildResult,
    ReviewHint,
    ReconResult,
    ReverseMode,
    ReverseStage,
    RouterResult,
    TaskCard,
)
from reverse_deepagent.evidence import EvidencePromotionResult, promote_evidence
from reverse_deepagent.runtime import (
    PLATFORM_NEUTRAL_ARTIFACT_CATEGORIES,
    WEB_ARTIFACT_CATEGORY_ALIASES,
    RuntimeArtifactManifest,
    RuntimeArtifactManifestEntry,
    RuntimeBackendCapabilities,
)


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

        manifest = RuntimeArtifactManifest(
            producer_backend_id="mock",
            producer_transport="in-process",
            target_platforms=["web"],
            entries=[
                RuntimeArtifactManifestEntry(
                    artifact_key="workspace_task_card",
                    path="/tmp/workspace/task-card.json",
                    category="workspace",
                    kind="json",
                    producer_backend_id="mock",
                )
            ],
        )
        self.assertEqual(manifest.model_dump(mode="json")["entries"][0]["kind"], "json")


    def test_review_hint_schema_rejects_extra_fields(self) -> None:
        hint = ReviewHint(
            severity="risk",
            category="replay",
            code="sample_replay_not_ok",
            message="Replay evidence is not ready.",
            evidence=["replay_result.ok=False"],
        )
        self.assertEqual(hint.model_dump(mode="json")["severity"], "risk")
        with self.assertRaises(Exception):
            ReviewHint(
                severity="risk",
                category="replay",
                code="bad",
                message="extra field should fail",
                evidence=[],
                unexpected=True,
            )


    def test_evidence_promotion_public_api_is_importable(self) -> None:
        result = promote_evidence([
            EvidenceItem(
                summary="源码命中 sign",
                kind=EvidenceKind.STATIC,
                source="search_in_sources",
                details={"count": 1, "sample": [{"line": "sign"}]},
                confidence=ConfidenceLevel.HIGH,
            )
        ])
        self.assertIsInstance(result, EvidencePromotionResult)
        self.assertEqual(result.summary["candidate_count"], 1)

    def test_platform_neutral_artifact_category_vocab_is_exported(self) -> None:
        self.assertIn("runtime-context", PLATFORM_NEUTRAL_ARTIFACT_CATEGORIES)
        self.assertIn("hook-timeline", PLATFORM_NEUTRAL_ARTIFACT_CATEGORIES)
        self.assertIn("static-analysis", PLATFORM_NEUTRAL_ARTIFACT_CATEGORIES)
        self.assertIn("rebuild", PLATFORM_NEUTRAL_ARTIFACT_CATEGORIES)
        self.assertEqual(WEB_ARTIFACT_CATEGORY_ALIASES["workspace"], "workspace")
        self.assertEqual(WEB_ARTIFACT_CATEGORY_ALIASES["rebuild"], "rebuild")


if __name__ == "__main__":
    unittest.main()
