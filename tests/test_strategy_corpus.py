import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.rebuild import write_rebuild_bundle
from reverse_deepagent.schemas import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceKind,
    ExecutionStatus,
    FinalResult,
    KeyFindings,
    ReverseMode,
    ReverseStage,
    TaskCard,
)
from reverse_deepagent.strategies import STRATEGY_SAMPLE_CORPUS, detect_algorithm_strategy, list_strategy_sample_corpus


def _final_result_for_sample(source_context: str, expected_sign: str, keyword: str, timestamp: int) -> FinalResult:
    task_card = TaskCard(
        target_url_or_file="http://127.0.0.1:8765/",
        target_param_or_api="sign",
        goal="生成纯算 replay",
        boundaries="strategy corpus test",
    )
    candidate = {
        "candidate_id": "script:1:buildSign",
        "function_name": "buildSign",
        "file_url": "http://127.0.0.1:8765/app.js",
        "script_id": "script",
        "line_number": 1,
        "source_context": source_context,
        "related_requests": [{"id": 1, "method": "POST", "url": "http://127.0.0.1:8765/api/search"}],
    }
    validation = {
        "candidate_id": candidate["candidate_id"],
        "function_name": "buildSign",
        "validation_status": "success",
        "checks": {
            "source_complete": True,
            "runtime_located": True,
            "runtime_invocation_ok": True,
            "sign_shape_ok": True,
            "replay_attempted": True,
            "replay_ok": True,
        },
        "sample_input": {"keyword": keyword, "timestamp": timestamp},
        "sample_output": {"sign": expected_sign, "callable_path": "window.buildSign", "invocation_result_type": "string"},
        "replay_result": {"attempted": True, "ok": True},
    }
    return FinalResult(
        task_card=task_card,
        mode=ReverseMode.FIND_ENTRY,
        stage=ReverseStage.REPLAY_DELIVERY,
        status=ExecutionStatus.SUCCESS,
        key_findings=KeyFindings(facts=["strategy corpus sample"]),
        evidence=[
            EvidenceItem(
                summary="candidate",
                kind=EvidenceKind.STATIC,
                source="function_candidate_card",
                details={"count": 1, "candidates": [candidate]},
                confidence=ConfidenceLevel.HIGH,
            ),
            EvidenceItem(
                summary="validation",
                kind=EvidenceKind.DYNAMIC,
                source="function_validation_result",
                details={"count": 1, "validations": [validation]},
                confidence=ConfidenceLevel.HIGH,
            ),
            EvidenceItem(
                summary="summary",
                kind=EvidenceKind.NOTE,
                source="function_validation_summary",
                details={
                    "total": 1,
                    "success_count": 1,
                    "failed_count": 0,
                    "replay_ready": True,
                    "best_candidate_id": candidate["candidate_id"],
                    "best_function_name": "buildSign",
                },
                confidence=ConfidenceLevel.HIGH,
            ),
        ],
        artifacts=[],
        next_action="extract_pure_logic_and_build_replay",
        confidence=ConfidenceLevel.HIGH,
    )


class StrategyCorpusTests(unittest.TestCase):
    def test_corpus_metadata_is_serializable(self) -> None:
        metadata = list_strategy_sample_corpus()
        self.assertGreaterEqual(len(metadata), 7)
        self.assertEqual({item["sample_id"] for item in metadata}, {sample.sample_id for sample in STRATEGY_SAMPLE_CORPUS})

    def test_corpus_detects_expected_strategy_ids(self) -> None:
        for sample in STRATEGY_SAMPLE_CORPUS:
            with self.subTest(sample_id=sample.sample_id):
                strategy = detect_algorithm_strategy(sample.source_context)
                self.assertEqual(strategy["id"], sample.strategy_id)
                self.assertTrue(strategy["supported"])

    def test_corpus_generated_sign_rebuilds_self_check(self) -> None:
        for sample in STRATEGY_SAMPLE_CORPUS:
            with self.subTest(sample_id=sample.sample_id):
                final_result = _final_result_for_sample(sample.source_context, sample.expected_sign, sample.keyword, sample.timestamp)
                with tempfile.TemporaryDirectory() as tmpdir:
                    rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
                    self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
                    self.assertEqual(rebuild.rebuild_plan["algorithm_strategy"]["id"], sample.strategy_id)
                    sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
                    result = subprocess.run(
                        [sys.executable, str(sign_rebuild_path)],
                        check=True,
                        text=True,
                        capture_output=True,
                    )
                    self.assertEqual(result.stdout.strip(), sample.expected_sign)


if __name__ == "__main__":
    unittest.main()
