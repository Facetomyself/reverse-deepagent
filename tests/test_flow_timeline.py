import unittest

from reverse_deepagent.browser.hooks import FlowTimelineManager, FlowTimelineSpec


class FlowTimelineManagerTests(unittest.TestCase):
    def test_build_continues_previous_timeline_and_normalizes_sources(self) -> None:
        spec = FlowTimelineSpec.from_context(
            {
                "flow_id": "sign-flow",
                "run_id": "run-2",
                "request_id": "req-2",
                "previous_flow_timeline": {
                    "flow_id": "sign-flow",
                    "entries": [
                        {
                            "sequence": 0,
                            "flow_id": "sign-flow",
                            "run_id": "run-1",
                            "source": "network_requests",
                            "type": "network.request",
                            "payload": {"url": "/api/old"},
                        }
                    ],
                },
                "network_requests": {"items": [{"url": "https://example.test/api/sign?x=1", "method": "POST", "requestId": "req-2"}]},
                "request_initiators": {
                    "items": [
                        {
                            "requestId": "req-2",
                            "url": "https://example.test/api/sign?x=1",
                            "method": "POST",
                            "initiator": {
                                "type": "script",
                                "stack": {"callFrames": [{"functionName": "buildSign"}]},
                            },
                        }
                    ]
                },
                "hook_timeline": {"snapshot": {"events": [{"type": "fetch", "payload": {"url": "/api/sign", "method": "POST", "path": "window.buildSign", "functionName": "buildSign"}}]}},
                "debugger_timeline": {"entries": [{"type": "breakpoint.hit", "callFrameId": "cf-1"}]},
                "replay_validation": {"validations": [{"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": True}]},
            }
        )

        result = FlowTimelineManager().build(spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.continued_from_previous)
        self.assertEqual(result.previous_entry_count, 1)
        self.assertEqual(result.new_entry_count, 5)
        self.assertEqual(len(result.entries), 6)
        self.assertEqual([entry["sequence"] for entry in result.entries], [0, 1, 2, 3, 4, 5])
        self.assertEqual(result.entries[1]["type"], "network.request")
        self.assertEqual(result.entries[2]["type"], "network.request")
        self.assertEqual(result.entries[3]["type"], "hook.fetch")
        self.assertEqual(result.entries[4]["type"], "debugger.breakpoint.hit")
        self.assertEqual(result.entries[5]["type"], "replay.validation")
        self.assertEqual(result.entries[1]["request_id"], "req-2")
        network_corr = result.entries[1]["correlation"]
        self.assertEqual(network_corr["request_id"], "req-2")
        self.assertEqual(network_corr["url_path"], "/api/sign")
        self.assertEqual(network_corr["method"], "POST")
        self.assertEqual(network_corr["confidence"], "medium")
        self.assertIn("request_id=req-2", network_corr["hints"])
        self.assertIn("url_path=/api/sign", network_corr["hints"])
        initiator_corr = result.entries[2]["correlation"]
        self.assertIn("buildSign", initiator_corr["function_names"])
        self.assertEqual(initiator_corr["request_id"], "req-2")
        hook_corr = result.entries[3]["correlation"]
        self.assertEqual(hook_corr["hook_paths"], ["window.buildSign"])
        self.assertEqual(hook_corr["url_path"], "/api/sign")
        replay_corr = result.entries[5]["correlation"]
        self.assertIn("script-1:buildSign", replay_corr["candidate_ids"])
        self.assertIn("buildSign", replay_corr["function_names"])
        self.assertEqual(replay_corr["confidence"], "low")
        self.assertEqual(result.source_counts["network_requests"], 1)
        self.assertEqual(result.source_counts["request_initiators"], 1)
        self.assertEqual(result.source_counts["hook_timeline"], 1)
        self.assertEqual(result.source_counts["debugger_timeline"], 1)
        self.assertEqual(result.source_counts["replay_validation"], 1)
        groups_by_strategy = {group["strategy"]: group for group in result.correlation_groups}
        self.assertEqual(len(result.correlation_groups), 3)
        self.assertEqual(groups_by_strategy["request_id"]["key"], {"request_id": "req-2"})
        self.assertEqual(groups_by_strategy["request_id"]["entry_sequences"], [1, 2])
        self.assertEqual(groups_by_strategy["request_id"]["confidence"], "medium")
        self.assertFalse(groups_by_strategy["request_id"]["stitching"])
        self.assertEqual(groups_by_strategy["request_id"]["verification"]["status"], "reviewable")
        self.assertIn("runtime_hook", groups_by_strategy["request_id"]["verification"]["missing_for_ready"])
        self.assertEqual(groups_by_strategy["url_path_method"]["key"], {"url_path": "/api/sign", "method": "POST"})
        self.assertEqual(groups_by_strategy["url_path_method"]["entry_sequences"], [1, 2, 3])
        self.assertEqual(groups_by_strategy["url_path_method"]["verification"]["status"], "reviewable")
        self.assertEqual(groups_by_strategy["url_path_method"]["verification"]["missing_for_ready"], ["replay_validation"])
        self.assertEqual(groups_by_strategy["function_name"]["key"], {"function_name": "buildSign"})
        self.assertEqual(groups_by_strategy["function_name"]["entry_sequences"], [2, 3, 5])
        self.assertEqual(groups_by_strategy["function_name"]["scope"], "correlation-hints-only")
        self.assertEqual(groups_by_strategy["function_name"]["verification"]["status"], "ready_for_manual_stitch_review")
        self.assertEqual(groups_by_strategy["function_name"]["verification"]["missing_for_ready"], [])
        self.assertFalse(groups_by_strategy["function_name"]["verification"]["automatic_stitching"])
        self.assertEqual(len(result.stitch_candidates), 3)
        candidates_by_group = {candidate["group_id"]: candidate for candidate in result.stitch_candidates}
        ready_candidate = candidates_by_group[groups_by_strategy["function_name"]["group_id"]]
        self.assertEqual(ready_candidate["candidate_id"], "stitch-1")
        self.assertEqual(ready_candidate["readiness"], "ready_for_manual_stitch_review")
        self.assertEqual(ready_candidate["confidence"], "medium")
        self.assertEqual(ready_candidate["strategy"], "function_name")
        self.assertEqual(ready_candidate["path_length"], 3)
        self.assertFalse(ready_candidate["automatic_stitching"])
        self.assertFalse(ready_candidate["stitching"])
        self.assertEqual(ready_candidate["scope"], "manual-stitch-candidate-only")
        self.assertEqual(ready_candidate["next_action"], "manual_stitch_review")
        self.assertTrue(ready_candidate["evidence"]["request_initiator"])
        self.assertTrue(ready_candidate["evidence"]["runtime_hook"])
        self.assertTrue(ready_candidate["evidence"]["replay_validation"])
        reviewable_candidate = candidates_by_group[groups_by_strategy["url_path_method"]["group_id"]]
        self.assertEqual(reviewable_candidate["readiness"], "reviewable")
        self.assertEqual(reviewable_candidate["confidence"], "low")
        self.assertIn("replay_validation", reviewable_candidate["missing_for_ready"])
        self.assertEqual(reviewable_candidate["next_action"], "collect_missing_evidence_or_review_manually")
        result_dict = result.to_dict()
        self.assertEqual(result_dict["correlation_group_count"], 3)
        self.assertEqual(result_dict["correlation_groups"][0]["stitching"], False)
        self.assertEqual(result_dict["stitch_candidate_count"], 3)
        self.assertEqual(result_dict["stitch_candidates"][0]["automatic_stitching"], False)

    def test_missing_inputs_is_not_a_flow_timeline_request(self) -> None:
        self.assertIsNone(FlowTimelineSpec.from_context({"flow_id": "empty"}))

    def test_correlation_group_with_single_evidence_kind_stays_weak(self) -> None:
        spec = FlowTimelineSpec.from_context(
            {
                "flow_id": "weak-flow",
                "replay_validation": {
                    "validations": [
                        {"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": True},
                        {"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": False},
                    ]
                },
            }
        )

        result = FlowTimelineManager().build(spec)

        groups_by_strategy = {group["strategy"]: group for group in result.correlation_groups}
        self.assertEqual(groups_by_strategy["candidate_id"]["verification"]["status"], "weak")
        self.assertEqual(groups_by_strategy["candidate_id"]["verification"]["evidence"]["replay_validation"], True)
        self.assertIn("request_initiator", groups_by_strategy["candidate_id"]["verification"]["missing_for_ready"])
        self.assertFalse(groups_by_strategy["candidate_id"]["verification"]["automatic_stitching"])
        self.assertEqual(result.stitch_candidates, [])
        self.assertEqual(result.to_dict()["stitch_candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
