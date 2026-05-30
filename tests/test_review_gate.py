import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.coordinator import run_reverse_pipeline
from reverse_deepagent.evidence import promote_evidence
from reverse_deepagent.review_gate import ReviewGateResult, evaluate_review_gate, review_gate_workspace_payload
from reverse_deepagent.schemas import ConfidenceLevel, EvidenceItem, EvidenceKind, ExecutionStatus, RebuildResult


class ReviewGateTests(unittest.TestCase):
    def test_gate_passes_ready_plan_without_blocking_hints(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={
                "ready": True,
                "review_hints": [
                    {
                        "severity": "info",
                        "category": "strategy",
                        "code": "pure_strategy_detected",
                        "message": "Pure strategy detected.",
                        "evidence": ["strategy=sig_keyword_timestamp_template"],
                    }
                ],
            },
            next_action="run_replay_demo_or_integrate_scrapy",
        )
        evidence = promote_evidence(
            [
                EvidenceItem(
                    summary="验证摘要 replay ready",
                    kind=EvidenceKind.NOTE,
                    source="function_validation_summary",
                    anchor="candidate-1",
                    details={"replay_ready": True, "best_candidate_id": "candidate-1"},
                    confidence=ConfidenceLevel.HIGH,
                )
            ]
        )
        gate = evaluate_review_gate(rebuild, evidence)
        self.assertIsInstance(gate, ReviewGateResult)
        self.assertEqual(gate.status, "pass")
        self.assertFalse(gate.blocked)
        self.assertEqual(gate.next_action, "delivery_allowed")
        self.assertEqual(gate.info_hint_codes, ["pure_strategy_detected"])

    def test_gate_blocks_risk_hints_even_when_plan_claims_ready(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={
                "ready": True,
                "review_hints": [
                    {
                        "severity": "risk",
                        "category": "replay",
                        "code": "sample_replay_not_ok",
                        "message": "Replay failed.",
                        "evidence": ["replay_result.ok=False"],
                    }
                ],
            },
            next_action="manual_review",
        )
        evidence = promote_evidence(
            [
                EvidenceItem(
                    summary="验证摘要 replay ready",
                    kind=EvidenceKind.NOTE,
                    source="function_validation_summary",
                    anchor="candidate-1",
                    details={"replay_ready": True},
                    confidence=ConfidenceLevel.HIGH,
                )
            ]
        )
        gate = evaluate_review_gate(rebuild, evidence)
        self.assertEqual(gate.status, "block")
        self.assertTrue(gate.blocked)
        self.assertEqual(gate.blocking_hint_codes, ["sample_replay_not_ok"])
        self.assertIn("risk_review_hints_present", gate.reasons)

    def test_gate_blocks_ready_plan_without_validated_evidence(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={"ready": True, "review_hints": []},
            next_action="run_replay_demo_or_integrate_scrapy",
        )
        evidence = promote_evidence(
            [
                EvidenceItem(
                    summary="只有一句备注",
                    kind=EvidenceKind.NOTE,
                    source="manual_note",
                    details={},
                    confidence=ConfidenceLevel.MEDIUM,
                )
            ]
        )
        gate = evaluate_review_gate(rebuild, evidence)
        self.assertEqual(gate.status, "block")
        self.assertTrue(gate.blocked)
        self.assertIn("validated_evidence_missing", gate.reasons)

    def test_gate_blocks_ready_plan_without_promoted_evidence(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={"ready": True, "review_hints": []},
            next_action="run_replay_demo_or_integrate_scrapy",
        )
        evidence = promote_evidence(
            [
                EvidenceItem(
                    summary="中等置信人工验证备注",
                    kind=EvidenceKind.NOTE,
                    source="manual_review",
                    details={"observed": True},
                    confidence=ConfidenceLevel.MEDIUM,
                )
            ]
        )
        self.assertEqual(evidence.summary["validated_count"], 1)
        self.assertEqual(evidence.summary["promoted_count"], 0)
        gate = evaluate_review_gate(rebuild, evidence)
        self.assertEqual(gate.status, "block")
        self.assertTrue(gate.blocked)
        self.assertIn("promoted_evidence_missing", gate.reasons)

    def test_gate_warns_for_warning_hints_without_risk(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={
                "ready": True,
                "review_hints": [
                    {
                        "severity": "warning",
                        "category": "runtime_context",
                        "code": "context_aware_rebuild",
                        "message": "Context aware rebuild.",
                        "evidence": ["runtime_context_required=localStorage"],
                    }
                ],
            },
            next_action="manual_review_before_delivery",
        )
        evidence = promote_evidence(
            [
                EvidenceItem(
                    summary="运行时上下文已捕获",
                    kind=EvidenceKind.STORAGE,
                    source="runtime_context",
                    anchor="localStorage",
                    details={"captured_requirements": ["localStorage"]},
                    confidence=ConfidenceLevel.HIGH,
                )
            ]
        )
        gate = evaluate_review_gate(rebuild, evidence)
        self.assertEqual(gate.status, "warn")
        self.assertFalse(gate.blocked)
        self.assertEqual(gate.warning_hint_codes, ["context_aware_rebuild"])
        payload = review_gate_workspace_payload(gate)
        self.assertEqual(payload["status"], "warn")

    def test_invalid_review_hint_payload_blocks_delivery(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={"ready": True, "review_hints": [{"not": "a valid hint"}]},
            next_action="manual_review",
        )
        gate = evaluate_review_gate(rebuild, promote_evidence([]))
        self.assertEqual(gate.status, "block")
        self.assertIn("invalid_review_hint", gate.blocking_hint_codes)

    def test_web_pipeline_writes_review_gate_artifact_and_manifest_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign 入口，并给出下一步建议",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="mock",
            )
            self.assertIn("workspace_review_gate", output.artifacts)
            gate = json.loads(Path(output.artifacts["workspace_review_gate"]).read_text(encoding="utf-8"))
            self.assertEqual(gate["status"], "pass")
            self.assertFalse(gate["blocked"])
            self.assertEqual(gate["next_action"], "delivery_allowed")
            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            self.assertEqual(manifest_by_key["workspace_review_gate"]["category"], "triage")
            index = json.loads(Path(output.artifacts["index"]).read_text(encoding="utf-8"))
            self.assertEqual(index["review_gate"]["status"], "pass")
            self.assertTrue(Path(index["review_gate_artifact"]).exists())

    def test_gate_blocks_pending_flow_stitch_proposal_review_requirement(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={"ready": True, "review_hints": []},
            next_action="run_replay_demo_or_integrate_scrapy",
        )
        evidence = promote_evidence(
            [
                EvidenceItem(
                    summary="验证摘要 replay ready",
                    kind=EvidenceKind.NOTE,
                    source="function_validation_summary",
                    anchor="candidate-1",
                    details={"replay_ready": True, "best_candidate_id": "candidate-1"},
                    confidence=ConfidenceLevel.HIGH,
                ),
                EvidenceItem(
                    summary="Native Web recon flow timeline assembled",
                    kind=EvidenceKind.NOTE,
                    source="flow_timeline",
                    details={
                        "stitch_proposals": [
                            {
                                "proposal_id": "stitch-proposal-1",
                                "candidate_id": "stitch-1",
                                "group_id": "cg-1",
                                "strategy": "function_name",
                                "scope": "review-gated-stitch-proposal-only",
                                "review_decision": {
                                    "status": "pending_review",
                                    "approved": False,
                                    "review_required": True,
                                },
                                "blocking_conditions": ["missing_reviewer_approval"],
                            }
                        ]
                    },
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ]
        )

        gate = evaluate_review_gate(rebuild, evidence)

        self.assertEqual(gate.status, "block")
        self.assertTrue(gate.blocked)
        self.assertEqual(gate.next_action, "review_stitch_proposals_before_delivery")
        self.assertEqual(gate.evidence_review_required_count, 1)
        self.assertEqual(
            gate.evidence_review_required_codes,
            ["flow_timeline_stitch_proposal_pending_review"],
        )
        self.assertIn("evidence_review_required", gate.reasons)
        self.assertIn("flow_timeline_stitch_proposal_pending_review", gate.reasons)
        self.assertEqual(gate.evidence_review_required_items[0]["proposal_id"], "stitch-proposal-1")

    def test_gate_does_not_block_approved_flow_stitch_proposal_review_requirement(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={"ready": True, "review_hints": []},
            next_action="run_replay_demo_or_integrate_scrapy",
        )
        evidence = promote_evidence(
            [
                EvidenceItem(
                    summary="验证摘要 replay ready",
                    kind=EvidenceKind.NOTE,
                    source="function_validation_summary",
                    anchor="candidate-1",
                    details={"replay_ready": True, "best_candidate_id": "candidate-1"},
                    confidence=ConfidenceLevel.HIGH,
                ),
                EvidenceItem(
                    summary="Native Web recon flow timeline assembled",
                    kind=EvidenceKind.NOTE,
                    source="flow_timeline",
                    details={
                        "stitch_proposals": [
                            {
                                "proposal_id": "stitch-proposal-1",
                                "candidate_id": "stitch-1",
                                "group_id": "cg-1",
                                "strategy": "function_name",
                                "scope": "review-gated-stitch-proposal-only",
                                "review_decision": {
                                    "status": "approved",
                                    "approved": True,
                                    "review_required": True,
                                },
                            }
                        ]
                    },
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ]
        )

        gate = evaluate_review_gate(rebuild, evidence)

        self.assertEqual(gate.status, "pass")
        self.assertFalse(gate.blocked)
        self.assertEqual(gate.next_action, "delivery_allowed")
        self.assertEqual(gate.evidence_review_required_count, 0)
        self.assertEqual(gate.evidence_review_required_codes, [])


if __name__ == "__main__":
    unittest.main()
