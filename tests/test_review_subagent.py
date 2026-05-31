import unittest
from pathlib import Path

from reverse_deepagent.agent import build_reverse_agent
from reverse_deepagent.evidence import promote_evidence
from reverse_deepagent.schemas import ConfidenceLevel, EvidenceItem, EvidenceKind, ExecutionStatus, RebuildResult
from reverse_deepagent.subagents.review import (
    REVIEW_SUBAGENT_DESCRIPTION,
    REVIEW_SUBAGENT_NAME,
    build_review_subagent,
    load_review_prompt,
)
from reverse_deepagent.tools.review_tools import make_evaluate_review_gate_tool


class ToolFriendlyFakeModel:
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


class ReviewSubagentTests(unittest.TestCase):
    def test_evaluate_review_gate_tool_is_read_only_and_blocks_pending_review(self) -> None:
        rebuild = RebuildResult(
            status=ExecutionStatus.SUCCESS,
            rebuild_plan={"ready": True, "review_hints": []},
            next_action="run_replay_demo_or_integrate_scrapy",
        )
        evidence = promote_evidence(
            [
                EvidenceItem(
                    summary="pending stitch proposal",
                    kind=EvidenceKind.NOTE,
                    source="flow_timeline",
                    anchor="proposal-1",
                    confidence=ConfidenceLevel.HIGH,
                    details={
                        "stitch_proposals": [
                            {
                                "proposal_id": "proposal-1",
                                "scope": "review-gated-stitch-proposal-only",
                                "review_decision": {"status": "pending_review", "review_required": True},
                                "blocking_conditions": ["missing_reviewer_approval"],
                            }
                        ]
                    },
                )
            ]
        )
        tool = make_evaluate_review_gate_tool()

        payload = tool(rebuild.model_dump_json(), evidence.model_dump_json())

        self.assertEqual(payload["status"], "block")
        self.assertTrue(payload["blocked"])
        self.assertEqual(payload["next_action"], "review_stitch_proposals_before_delivery")
        self.assertEqual(payload["evidence_review_required_count"], 1)
        self.assertTrue(payload["side_effect_policy"]["read_only"])
        self.assertFalse(payload["side_effect_policy"]["files_mutated"])
        self.assertFalse(payload["side_effect_policy"]["delivery_executed"])
        self.assertFalse(payload["side_effect_policy"]["external_delivery_performed"])
        self.assertFalse(payload["side_effect_policy"]["review_decision_recorded"])

    def test_evaluate_review_gate_tool_can_pass_ready_rebuild_with_promoted_evidence(self) -> None:
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
                    summary="validated replay ready",
                    kind=EvidenceKind.NOTE,
                    source="function_validation_summary",
                    anchor="candidate-1",
                    details={"replay_ready": True, "best_candidate_id": "candidate-1"},
                    confidence=ConfidenceLevel.HIGH,
                )
            ]
        )
        payload = make_evaluate_review_gate_tool()(rebuild.model_dump_json(), evidence.model_dump_json())

        self.assertEqual(payload["status"], "pass")
        self.assertFalse(payload["blocked"])
        self.assertEqual(payload["next_action"], "delivery_allowed")
        self.assertEqual(payload["info_hint_codes"], ["pure_strategy_detected"])

    def test_build_review_subagent_exposes_read_only_gate_tool(self) -> None:
        subagent = build_review_subagent()

        self.assertEqual(subagent["name"], REVIEW_SUBAGENT_NAME)
        self.assertEqual(subagent["description"], REVIEW_SUBAGENT_DESCRIPTION)
        self.assertIn("Review Subagent", subagent["system_prompt"])
        self.assertEqual({tool.__name__ for tool in subagent["tools"]}, {"evaluate_delivery_review_gate"})

    def test_prompt_loader_supports_custom_path(self) -> None:
        path = Path(__file__).resolve().parents[1] / "src/reverse_deepagent/prompts/review.txt"
        self.assertIn("read-only review gate", load_review_prompt(path))

    def test_default_agent_includes_review_subagent_without_runtime(self) -> None:
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
        self.assertIn("review", names)
        self.assertLess(names.index("router"), names.index("review"))
        self.assertLess(names.index("review"), names.index("rebuild"))


if __name__ == "__main__":
    unittest.main()
