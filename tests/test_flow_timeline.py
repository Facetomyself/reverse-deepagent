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
                "network_requests": {"items": [{"url": "/api/sign", "method": "POST", "requestId": "req-2"}]},
                "hook_timeline": {"snapshot": {"events": [{"type": "fetch", "payload": {"url": "/api/sign"}}]}},
                "debugger_timeline": {"entries": [{"type": "breakpoint.hit", "callFrameId": "cf-1"}]},
                "replay_validation": {"validations": [{"function_name": "buildSign", "replay_ok": True}]},
            }
        )

        result = FlowTimelineManager().build(spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.continued_from_previous)
        self.assertEqual(result.previous_entry_count, 1)
        self.assertEqual(result.new_entry_count, 4)
        self.assertEqual(len(result.entries), 5)
        self.assertEqual([entry["sequence"] for entry in result.entries], [0, 1, 2, 3, 4])
        self.assertEqual(result.entries[1]["type"], "network.request")
        self.assertEqual(result.entries[2]["type"], "hook.fetch")
        self.assertEqual(result.entries[3]["type"], "debugger.breakpoint.hit")
        self.assertEqual(result.entries[4]["type"], "replay.validation")
        self.assertEqual(result.entries[1]["request_id"], "req-2")
        self.assertEqual(result.source_counts["network_requests"], 1)
        self.assertEqual(result.source_counts["hook_timeline"], 1)
        self.assertEqual(result.source_counts["debugger_timeline"], 1)
        self.assertEqual(result.source_counts["replay_validation"], 1)

    def test_missing_inputs_is_not_a_flow_timeline_request(self) -> None:
        self.assertIsNone(FlowTimelineSpec.from_context({"flow_id": "empty"}))


if __name__ == "__main__":
    unittest.main()
