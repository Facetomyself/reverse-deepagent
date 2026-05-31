import json
import unittest
from pathlib import Path

from reverse_deepagent.agent import build_reverse_agent
from reverse_deepagent.subagents.timeline import (
    TIMELINE_SUBAGENT_DESCRIPTION,
    TIMELINE_SUBAGENT_NAME,
    build_timeline_subagent,
    load_timeline_prompt,
)
from reverse_deepagent.tools.timeline_tools import FLOW_TIMELINE_REVIEW_VERSION, make_review_flow_timeline_tool


class ToolFriendlyFakeModel:
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


class TimelineSubagentTests(unittest.TestCase):
    def test_review_flow_timeline_blocks_pending_stitch_proposal(self) -> None:
        timeline = {
            "entries": [
                {"id": "entry-1", "source": "network", "correlation": {"request_id": "r1"}},
                {"id": "entry-2", "source": "hook", "correlation": {"request_id": "r1"}},
            ],
            "correlation_groups": [
                {
                    "group_id": "group-1",
                    "verification": {"status": "ready_for_manual_stitch_review"},
                }
            ],
            "stitch_candidates": [{"candidate_id": "candidate-1"}],
            "stitch_proposals": [
                {
                    "proposal_id": "proposal-1",
                    "review_decision": {"status": "pending_review", "review_required": True},
                    "blocking_conditions": ["missing_reviewer_approval"],
                }
            ],
            "auto_stitch_dry_runs": [{"candidate_id": "candidate-1", "would_materialize": False}],
            "auto_stitch_policy_decisions": [{"decision_id": "decision-1", "status": "ready_for_review_gate"}],
        }
        payload = make_review_flow_timeline_tool()(json.dumps(timeline))

        self.assertEqual(payload["version"], FLOW_TIMELINE_REVIEW_VERSION)
        self.assertEqual(payload["status"], "block")
        self.assertTrue(payload["blocked"])
        self.assertEqual(payload["next_action"], "review_stitch_proposals_before_materialization_or_delivery")
        self.assertEqual(payload["summary"]["entry_count"], 2)
        self.assertEqual(payload["summary"]["entry_source_counts"], {"hook": 1, "network": 1})
        self.assertEqual(payload["summary"]["review_ready_group_count"], 1)
        self.assertEqual(payload["summary"]["pending_stitch_proposal_count"], 1)
        self.assertIn("pending_stitch_proposals_require_review", payload["blockers"])
        self.assertEqual(payload["review_required_items"][0]["code"], "flow_timeline_stitch_proposal_pending_review")
        self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
        self.assertFalse(payload["side_effect_policy"]["timeline_materialized"])
        self.assertFalse(payload["side_effect_policy"]["review_decision_recorded"])
        self.assertFalse(payload["side_effect_policy"]["delivery_executed"])

    def test_review_flow_timeline_passes_approved_timeline_without_blockers(self) -> None:
        timeline = {
            "entries": [{"id": "entry-1", "source": "replay"}],
            "correlation_groups": [{"verification": {"status": "reviewable"}}],
            "stitch_proposals": [
                {
                    "proposal_id": "proposal-approved",
                    "review_decision": {"status": "approved", "approved": True},
                }
            ],
            "auto_stitch_policy_decisions": [{"decision_id": "decision-1", "status": "ready_for_review_gate"}],
            "auto_stitch_materialization_results": [{"approved": True, "materialized": True}],
        }

        payload = make_review_flow_timeline_tool()(json.dumps(timeline))

        self.assertEqual(payload["status"], "pass")
        self.assertFalse(payload["blocked"])
        self.assertEqual(payload["next_action"], "timeline_review_passed")
        self.assertEqual(payload["summary"]["approved_stitch_proposal_count"], 1)
        self.assertEqual(payload["summary"]["approved_materialization_count"], 1)

    def test_build_timeline_subagent_exposes_read_only_review_tool(self) -> None:
        subagent = build_timeline_subagent()

        self.assertEqual(subagent["name"], TIMELINE_SUBAGENT_NAME)
        self.assertEqual(subagent["description"], TIMELINE_SUBAGENT_DESCRIPTION)
        self.assertIn("Timeline Subagent", subagent["system_prompt"])
        self.assertEqual({tool.__name__ for tool in subagent["tools"]}, {"review_flow_timeline"})

    def test_prompt_loader_supports_custom_path(self) -> None:
        path = Path(__file__).resolve().parents[1] / "src/reverse_deepagent/prompts/timeline.txt"
        self.assertIn("read-only timeline review", load_timeline_prompt(path))

    def test_default_agent_includes_timeline_before_review(self) -> None:
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
        self.assertIn("timeline", names)
        self.assertLess(names.index("router"), names.index("timeline"))
        self.assertLess(names.index("timeline"), names.index("review"))
        self.assertLess(names.index("review"), names.index("rebuild"))


if __name__ == "__main__":
    unittest.main()
