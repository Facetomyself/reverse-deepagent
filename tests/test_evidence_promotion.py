import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.coordinator import run_platform_pipeline, run_reverse_pipeline
from reverse_deepagent.evidence import promote_evidence, promotion_workspace_payloads
from reverse_deepagent.adapters.platforms import MiniProgramDevtoolsRuntime
from reverse_deepagent.schemas import ArtifactKind, ArtifactRef, ConfidenceLevel, EvidenceItem, EvidenceKind


class EvidencePromotionTests(unittest.TestCase):
    def test_promote_evidence_builds_candidate_validated_and_promoted_buckets(self) -> None:
        evidence = [
            EvidenceItem(
                summary="源码上下文已确认 buildSign",
                kind=EvidenceKind.STATIC,
                source="get_script_source",
                anchor="script-1:10",
                details={"count": 1, "sample": [{"source": "function buildSign() {}"}]},
                confidence=ConfidenceLevel.HIGH,
            ),
            EvidenceItem(
                summary="验证摘要已确认 replay ready",
                kind=EvidenceKind.NOTE,
                source="function_validation_summary",
                anchor="candidate-1",
                details={"replay_ready": True, "best_candidate_id": "candidate-1"},
                confidence=ConfidenceLevel.HIGH,
            ),
            EvidenceItem(
                summary="工具不可用",
                kind=EvidenceKind.DYNAMIC,
                source="platform_tool_probe",
                details={"available": False},
                confidence=ConfidenceLevel.LOW,
            ),
        ]
        artifacts = [
            ArtifactRef(path="virtual://workspace/source-contexts.json", kind=ArtifactKind.JSON),
            ArtifactRef(path="virtual://workspace/function-validation-summary.json", kind=ArtifactKind.JSON),
        ]
        result = promote_evidence(evidence, artifacts)
        self.assertEqual(len(result.candidates), 3)
        self.assertGreaterEqual(len(result.validated), 2)
        self.assertGreaterEqual(len(result.promoted), 2)
        self.assertEqual(len(result.rejected), 1)
        by_source = {item.source: item for item in result.promoted}
        self.assertIn("get_script_source", by_source)
        self.assertIn("function_validation_summary", by_source)
        self.assertIn("virtual://workspace/source-contexts.json", by_source["get_script_source"].artifact_paths)
        payloads = promotion_workspace_payloads(result)
        self.assertIn("evidence-candidates.json", payloads)
        self.assertIn("evidence-validated.json", payloads)
        self.assertIn("evidence-promotion.json", payloads)
        self.assertEqual(payloads["evidence-promotion.json"]["summary"]["candidate_count"], 3)


    def test_candidate_below_threshold_is_not_validated(self) -> None:
        evidence = [
            EvidenceItem(
                summary="只有一句未锚定备注",
                kind=EvidenceKind.NOTE,
                source="manual_note",
                details={},
                confidence=ConfidenceLevel.MEDIUM,
            )
        ]
        result = promote_evidence(evidence)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.validated, [])
        self.assertEqual(result.promoted, [])
        self.assertEqual(result.rejected, [])
        self.assertEqual(result.summary["status"], "blocked")

    def test_web_pipeline_writes_evidence_promotion_artifacts_and_manifest_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign 入口，并给出下一步建议",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="mock",
            )
            self.assertIn("workspace_evidence_candidates", output.artifacts)
            self.assertIn("workspace_evidence_validated", output.artifacts)
            self.assertIn("workspace_evidence_promotion", output.artifacts)
            promotion = json.loads(Path(output.artifacts["workspace_evidence_promotion"]).read_text(encoding="utf-8"))
            self.assertGreater(promotion["summary"]["candidate_count"], 0)
            self.assertGreater(promotion["summary"]["validated_count"], 0)
            self.assertGreater(promotion["summary"]["promoted_count"], 0)
            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            self.assertEqual(manifest_by_key["workspace_evidence_candidates"]["category"], "evidence")
            self.assertEqual(manifest_by_key["workspace_evidence_validated"]["category"], "evidence")
            self.assertEqual(manifest_by_key["workspace_evidence_promotion"]["category"], "evidence")
            index = json.loads(Path(output.artifacts["index"]).read_text(encoding="utf-8"))
            self.assertIn("evidence_promotion", index)
            self.assertIn("evidence_artifacts", index)

    def test_platform_pipeline_writes_evidence_promotion_for_non_web_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_platform_pipeline(
                task_text="mini-program://demo 找 sign",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="mini-program-devtools",
                runtime=MiniProgramDevtoolsRuntime(),
            )
            self.assertIn("workspace_evidence_candidates", output.artifacts)
            self.assertIn("workspace_evidence_validated", output.artifacts)
            self.assertIn("workspace_evidence_promotion", output.artifacts)
            promotion = json.loads(Path(output.artifacts["workspace_evidence_promotion"]).read_text(encoding="utf-8"))
            self.assertGreater(promotion["summary"]["candidate_count"], 0)
            self.assertIn("summary", promotion)
            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            self.assertEqual(manifest_by_key["workspace_evidence_promotion"]["category"], "evidence")


if __name__ == "__main__":
    unittest.main()
