import unittest

from reverse_deepagent.browser.hooks import FlowTimelineManager, FlowTimelineSpec


class FlowTimelineManagerTests(unittest.TestCase):
    def _ready_flow_context(self) -> dict:
        return {
            "flow_id": "sign-flow",
            "run_id": "run-2",
            "request_id": "req-2",
            "network_requests": {"items": [{"url": "https://example.test/api/sign?x=1", "method": "POST", "requestId": "req-2"}]},
            "request_initiators": {
                "items": [
                    {
                        "requestId": "req-2",
                        "url": "https://example.test/api/sign?x=1",
                        "method": "POST",
                        "initiator": {"type": "script", "stack": {"callFrames": [{"functionName": "buildSign"}]}},
                    }
                ]
            },
            "hook_timeline": {"snapshot": {"events": [{"type": "fetch", "payload": {"url": "/api/sign", "method": "POST", "path": "window.buildSign", "functionName": "buildSign"}}]}},
            "replay_validation": {"validations": [{"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": True}]},
        }

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
        self.assertEqual(len(result.auto_stitch_dry_runs), 3)
        dry_runs_by_candidate = {dry_run["candidate_id"]: dry_run for dry_run in result.auto_stitch_dry_runs}
        ready_dry_run = dry_runs_by_candidate[ready_candidate["candidate_id"]]
        self.assertEqual(ready_dry_run["scope"], "auto-stitch-dry-run-only")
        self.assertTrue(ready_dry_run["dry_run"])
        self.assertTrue(ready_dry_run["review_required"])
        self.assertFalse(ready_dry_run["would_materialize"])
        self.assertFalse(ready_dry_run["automatic_stitching"])
        self.assertFalse(ready_dry_run["stitching"])
        self.assertGreaterEqual(ready_dry_run["confidence_score"], 0.85)
        self.assertEqual(ready_dry_run["confidence"], "high")
        self.assertIn("dry_run_only", ready_dry_run["blocking_conditions"])
        self.assertIn("automatic_application_disabled", ready_dry_run["blocking_conditions"])
        self.assertIn("overlaps_with_", " ".join(ready_dry_run["conflict_reasons"]))
        self.assertEqual(ready_dry_run["next_action"], "review_auto_stitch_dry_run_before_materialization")
        reviewable_dry_run = dry_runs_by_candidate[reviewable_candidate["candidate_id"]]
        self.assertTrue(reviewable_dry_run["review_required"])
        self.assertFalse(reviewable_dry_run["would_materialize"])
        self.assertIn("missing_replay_validation", reviewable_dry_run["blocking_conditions"])
        self.assertIn("missing_for_ready=replay_validation", reviewable_dry_run["score_reasons"])
        self.assertEqual(len(result.auto_stitch_conflict_resolutions), 3)
        resolutions_by_candidate = {resolution["candidate_id"]: resolution for resolution in result.auto_stitch_conflict_resolutions}
        ready_resolution = resolutions_by_candidate[ready_candidate["candidate_id"]]
        self.assertEqual(ready_resolution["scope"], "auto-stitch-conflict-resolution-baseline")
        self.assertEqual(ready_resolution["status"], "review_required")
        self.assertEqual(ready_resolution["strategy"], "prefer_highest_confidence_review_required")
        self.assertEqual(ready_resolution["dry_run_id"], ready_dry_run["dry_run_id"])
        self.assertEqual(ready_resolution["unresolved_conflicts"], ready_dry_run["conflict_reasons"])
        self.assertEqual(ready_resolution["resolved_conflicts"], [])
        self.assertEqual(ready_resolution["selected_candidate_id"], ready_candidate["candidate_id"])
        self.assertTrue(ready_resolution["review_required"])
        self.assertFalse(ready_resolution["would_materialize"])
        self.assertFalse(ready_resolution["automatic_stitching"])
        self.assertEqual(result.auto_stitch_conflict_resolution_summary["resolution_count"], 3)
        self.assertEqual(result.auto_stitch_conflict_resolution_summary["conflict_count"], 3)
        self.assertEqual(result.auto_stitch_conflict_resolution_summary["unresolved_count"], 3)
        self.assertTrue(result.auto_stitch_conflict_resolution_summary["review_required"])
        self.assertFalse(result.auto_stitch_conflict_resolution_summary["would_materialize"])
        self.assertEqual(len(result.auto_stitch_policy_decisions), 3)
        policy_decisions_by_candidate = {decision["candidate_id"]: decision for decision in result.auto_stitch_policy_decisions}
        ready_policy_decision = policy_decisions_by_candidate[ready_candidate["candidate_id"]]
        self.assertEqual(ready_policy_decision["status"], "blocked")
        self.assertFalse(ready_policy_decision["would_materialize"])
        self.assertFalse(ready_policy_decision["automatic_stitching"])
        self.assertIn("conflict_review_required", ready_policy_decision["policy_blocking_conditions"])
        self.assertEqual(result.auto_stitch_policy_summary["decision_count"], 3)
        self.assertEqual(result.auto_stitch_policy_summary["eligible_for_review_gate_count"], 0)
        self.assertFalse(result.auto_stitch_policy_summary["automatic_materialization_enabled"])
        self.assertEqual(result.auto_stitch_materialization_plans, [])
        self.assertEqual(result.auto_stitch_materialization_summary["plan_count"], 0)
        self.assertFalse(result.auto_stitch_materialization_summary["writes_artifact"])
        self.assertEqual(len(result.stitch_proposals), 1)
        proposal = result.stitch_proposals[0]
        self.assertEqual(proposal["proposal_id"], "stitch-proposal-1")
        self.assertEqual(proposal["candidate_id"], ready_candidate["candidate_id"])
        self.assertEqual(proposal["group_id"], groups_by_strategy["function_name"]["group_id"])
        self.assertEqual(proposal["strategy"], "function_name")
        self.assertEqual(proposal["scope"], "review-gated-stitch-proposal-only")
        self.assertEqual(proposal["review_decision"]["status"], "pending_review")
        self.assertFalse(proposal["review_decision"]["approved"])
        self.assertTrue(proposal["review_decision"]["review_required"])
        self.assertIn("missing_reviewer_approval", proposal["blocking_conditions"])
        self.assertIn("automatic_application_disabled", proposal["blocking_conditions"])
        self.assertIn("confirm_replay_validation_matches_original_request_semantics", proposal["approval_requirements"])
        self.assertFalse(proposal["automatic_stitching"])
        self.assertFalse(proposal["stitching"])
        result_dict = result.to_dict()
        self.assertEqual(result_dict["correlation_group_count"], 3)
        self.assertEqual(result_dict["correlation_groups"][0]["stitching"], False)
        self.assertEqual(result_dict["stitch_candidate_count"], 3)
        self.assertEqual(result_dict["stitch_candidates"][0]["automatic_stitching"], False)
        self.assertEqual(result_dict["auto_stitch_dry_run_count"], 3)
        self.assertEqual(result_dict["auto_stitch_dry_runs"][0]["scope"], "auto-stitch-dry-run-only")
        self.assertFalse(result_dict["auto_stitch_dry_runs"][0]["automatic_stitching"])
        self.assertEqual(result_dict["auto_stitch_conflict_resolution_count"], 3)
        self.assertEqual(result_dict["auto_stitch_conflict_resolutions"][0]["scope"], "auto-stitch-conflict-resolution-baseline")
        self.assertFalse(result_dict["auto_stitch_conflict_resolution_summary"]["would_materialize"])
        self.assertEqual(result_dict["auto_stitch_policy_decision_count"], 3)
        self.assertEqual(result_dict["auto_stitch_policy_decisions"][0]["scope"], "auto-stitch-policy-decision-only")
        self.assertFalse(result_dict["auto_stitch_policy_summary"]["would_materialize"])
        self.assertEqual(result_dict["auto_stitch_materialization_plan_count"], 0)
        self.assertFalse(result_dict["auto_stitch_materialization_summary"]["would_materialize"])
        self.assertEqual(result_dict["stitch_proposal_count"], 1)
        self.assertEqual(result_dict["stitch_proposals"][0]["review_decision"]["status"], "pending_review")

    def test_auto_stitch_policy_can_mark_high_confidence_dry_run_for_review_gate_without_materializing(self) -> None:
        context = self._ready_flow_context()
        context["auto_stitch_policy"] = {
            "policy_id": "unit-policy",
            "min_confidence_score": 0.85,
            "allow_conflicts": True,
            "enable_automatic_materialization": True,
        }
        result = FlowTimelineManager().build(FlowTimelineSpec.from_context(context))

        self.assertEqual(result.auto_stitch_policy_summary["policy_id"], "unit-policy")
        self.assertEqual(result.auto_stitch_policy_summary["decision_count"], len(result.auto_stitch_dry_runs))
        self.assertEqual(result.auto_stitch_policy_summary["eligible_for_review_gate_count"], 1)
        self.assertFalse(result.auto_stitch_policy_summary["automatic_materialization_enabled"])
        ready_decisions = [decision for decision in result.auto_stitch_policy_decisions if decision["status"] == "ready_for_review_gate"]
        self.assertEqual(len(ready_decisions), 1)
        self.assertTrue(ready_decisions[0]["eligible_for_review_gate"])
        self.assertTrue(ready_decisions[0]["automatic_materialization_requested"])
        self.assertTrue(ready_decisions[0]["review_required"])
        self.assertFalse(ready_decisions[0]["would_materialize"])
        self.assertFalse(ready_decisions[0]["automatic_stitching"])
        self.assertIn("automatic_materialization_not_implemented", ready_decisions[0]["policy_blocking_conditions"])
        self.assertEqual(ready_decisions[0]["next_action"], "review_policy_eligible_candidate_before_materialization")
        self.assertEqual(len(result.auto_stitch_materialization_plans), 1)
        plan = result.auto_stitch_materialization_plans[0]
        self.assertEqual(plan["status"], "plan_ready_for_review")
        self.assertEqual(plan["materialization_mode"], "plan_only")
        self.assertEqual(plan["target_artifact"], "workspace/stitched-flow.json")
        self.assertEqual(plan["entry_sequences"], [1, 2, 3])
        self.assertTrue(plan["review_required"])
        self.assertFalse(plan["would_materialize"])
        self.assertFalse(plan["writes_artifact"])
        self.assertFalse(plan["automatic_stitching"])
        self.assertIsNotNone(plan["conflict_resolution"]["resolution_id"])
        self.assertEqual(plan["conflict_resolution"]["selected_candidate_id"], plan["candidate_id"])
        self.assertIn("missing_materialization_reviewer_approval", plan["policy_blocking_conditions"])
        self.assertEqual(plan["rollback_plan"]["strategy"], "do_not_write_until_reviewed")
        self.assertEqual(result.auto_stitch_materialization_summary["plan_count"], 1)
        self.assertEqual(result.auto_stitch_materialization_summary["eligible_decision_count"], 1)
        self.assertFalse(result.auto_stitch_materialization_summary["materialization_enabled"])
        self.assertFalse(result.auto_stitch_materialization_summary["writes_artifact"])
        self.assertEqual(result.auto_stitch_materialization_results, [])
        self.assertEqual(result.auto_stitch_materialization_result_summary["result_count"], 0)
        self.assertFalse(result.auto_stitch_materialization_result_summary["writes_artifact"])
        self.assertEqual(result.stitched_flows, [])

    def test_approved_auto_stitch_materialization_review_decision_materializes_plan(self) -> None:
        context = self._ready_flow_context()
        context["auto_stitch_policy"] = {
            "policy_id": "unit-policy",
            "min_confidence_score": 0.85,
            "allow_conflicts": True,
            "enable_automatic_materialization": True,
        }
        context["auto_stitch_materialization_review_decisions"] = [
            {
                "plan_id": "auto-stitch-materialization-plan-1",
                "status": "approved",
                "approved": True,
                "reviewer": "materialization-reviewer",
                "reviewed_at": "2026-05-31T09:00:00Z",
                "reason": "Plan path, conflict policy, and replay evidence are acceptable.",
            }
        ]

        result = FlowTimelineManager().build(FlowTimelineSpec.from_context(context))

        self.assertEqual(result.stitch_review_decisions, [])
        self.assertEqual(len(result.auto_stitch_materialization_review_decisions), 1)
        self.assertEqual(len(result.auto_stitch_materialization_plans), 1)
        plan = result.auto_stitch_materialization_plans[0]
        self.assertEqual(plan["status"], "approved_for_materialization")
        self.assertEqual(plan["materialization_mode"], "review_approved_plan")
        self.assertEqual(plan["review_decision"]["status"], "approved")
        self.assertTrue(plan["review_decision"]["approved"])
        self.assertFalse(plan["review_required"])
        self.assertNotIn("missing_materialization_reviewer_approval", plan["policy_blocking_conditions"])
        self.assertNotIn("automatic_materialization_not_implemented", plan["policy_blocking_conditions"])
        self.assertEqual(plan["next_action"], "materialize_review_approved_auto_stitch_plan")

        self.assertEqual(len(result.auto_stitch_materialization_results), 1)
        materialized = result.auto_stitch_materialization_results[0]
        self.assertEqual(materialized["status"], "materialized")
        self.assertEqual(materialized["plan_id"], "auto-stitch-materialization-plan-1")
        self.assertEqual(materialized["target_artifact"], "workspace/stitched-flow.json")
        self.assertEqual(materialized["entry_sequences"], [1, 2, 3])
        self.assertTrue(materialized["materialized"])
        self.assertTrue(materialized["writes_artifact"])
        self.assertTrue(materialized["would_materialize"])
        self.assertTrue(materialized["stitching"])
        self.assertFalse(materialized["automatic_stitching"])
        self.assertEqual(materialized["source"], "review_approved_auto_stitch_materialization_plan")
        self.assertEqual(materialized["audit"]["review_gate"], "auto_stitch_materialization_review_decision")
        self.assertEqual(materialized["rollback_plan"]["strategy"], "manual_revert_review_approved_materialization")
        self.assertIn("review_approved_not_fully_automatic", materialized["limitations"])

        self.assertEqual(result.auto_stitch_materialization_result_summary["result_count"], 1)
        self.assertEqual(result.auto_stitch_materialization_result_summary["materialized_count"], 1)
        self.assertEqual(result.auto_stitch_materialization_result_summary["approved_review_decision_count"], 1)
        self.assertTrue(result.auto_stitch_materialization_result_summary["writes_artifact"])
        self.assertFalse(result.auto_stitch_materialization_result_summary["automatic_stitching"])
        self.assertEqual(len(result.auto_stitch_materialization_audit_entries), 1)
        audit = result.auto_stitch_materialization_audit_entries[0]
        self.assertEqual(audit["status"], "audit_ready")
        self.assertEqual(audit["operation"], "write_stitched_flow")
        self.assertEqual(audit["transaction_id"], "auto-stitch-materialization-txn-1")
        self.assertEqual(audit["result_id"], "auto-stitch-materialization-result-1")
        self.assertEqual(audit["audit_artifact"], "workspace/stitched-flow-materialization-audit.json")
        self.assertEqual(audit["rollback_artifact"], "workspace/stitched-flow-rollback-plan.json")
        self.assertTrue(audit["writes_artifact"])
        self.assertFalse(audit["automatic_stitching"])
        self.assertIn("explicit_materialization_review_approved", audit["preconditions"])
        self.assertIn("rollback_plan_available_for_manual_revert", audit["postconditions"])
        self.assertEqual(result.auto_stitch_materialization_audit_summary["audit_count"], 1)
        self.assertEqual(result.auto_stitch_materialization_audit_summary["missing_audit_count"], 0)
        self.assertEqual(result.auto_stitch_materialization_audit_summary["transaction_count"], 1)
        self.assertEqual(len(result.auto_stitch_materialization_rollback_plans), 1)
        rollback = result.auto_stitch_materialization_rollback_plans[0]
        self.assertEqual(rollback["status"], "rollback_ready")
        self.assertEqual(rollback["rollback_mode"], "manual_review_required")
        self.assertEqual(rollback["transaction_id"], "auto-stitch-materialization-txn-1")
        self.assertEqual(rollback["audit_id"], audit["audit_id"])
        self.assertEqual(rollback["remove_selectors"]["materialization_result_id"], "auto-stitch-materialization-result-1")
        self.assertFalse(rollback["writes_artifact"])
        self.assertFalse(rollback["would_revert"])
        self.assertFalse(rollback["automatic_rollback"])
        self.assertFalse(rollback["automatic_stitching"])
        self.assertIn("confirm_review_gate_recomputed_after_rollback", rollback["verification_requirements"])
        self.assertEqual(result.auto_stitch_materialization_rollback_summary["rollback_plan_count"], 1)
        self.assertEqual(result.auto_stitch_materialization_rollback_summary["missing_rollback_plan_count"], 0)
        self.assertFalse(result.auto_stitch_materialization_rollback_summary["automatic_rollback"])
        self.assertEqual(len(result.auto_stitch_materialization_transactions), 1)
        transaction = result.auto_stitch_materialization_transactions[0]
        self.assertEqual(transaction["status"], "transaction_ready")
        self.assertEqual(transaction["transaction_id"], "auto-stitch-materialization-txn-1")
        self.assertEqual(transaction["result_id"], "auto-stitch-materialization-result-1")
        self.assertEqual(transaction["audit_id"], audit["audit_id"])
        self.assertEqual(transaction["rollback_id"], rollback["rollback_id"])
        self.assertTrue(transaction["integrity"]["has_materialization_result"])
        self.assertTrue(transaction["integrity"]["has_audit"])
        self.assertTrue(transaction["integrity"]["has_rollback_plan"])
        self.assertEqual(transaction["integrity"]["missing_links"], [])
        self.assertTrue(transaction["writes_artifact"])
        self.assertTrue(transaction["would_materialize"])
        self.assertFalse(transaction["would_revert"])
        self.assertFalse(transaction["automatic_rollback"])
        self.assertFalse(transaction["automatic_stitching"])
        self.assertTrue(transaction["transaction_log_only"])
        self.assertEqual(transaction["next_action"], "review_materialization_transaction_and_rollback_plan")
        self.assertEqual(result.auto_stitch_materialization_transaction_summary["transaction_count"], 1)
        self.assertEqual(result.auto_stitch_materialization_transaction_summary["ready_transaction_count"], 1)
        self.assertEqual(result.auto_stitch_materialization_transaction_summary["incomplete_transaction_count"], 0)
        self.assertEqual(result.auto_stitch_materialization_transaction_summary["missing_transaction_count"], 0)
        self.assertFalse(result.auto_stitch_materialization_transaction_summary["automatic_rollback"])
        self.assertTrue(result.auto_stitch_materialization_transaction_summary["transaction_log_only"])
        self.assertEqual(len(result.auto_stitch_rollback_execution_plans), 1)
        execution_plan = result.auto_stitch_rollback_execution_plans[0]
        self.assertEqual(execution_plan["status"], "rollback_execution_plan_ready_for_review")
        self.assertEqual(execution_plan["execution_mode"], "dry_run_only")
        self.assertEqual(execution_plan["transaction_id"], "auto-stitch-materialization-txn-1")
        self.assertEqual(execution_plan["rollback_id"], rollback["rollback_id"])
        self.assertTrue(execution_plan["dry_run"])
        self.assertTrue(execution_plan["review_required"])
        self.assertFalse(execution_plan["would_revert"])
        self.assertFalse(execution_plan["writes_artifact"])
        self.assertFalse(execution_plan["target_artifact_mutated"])
        self.assertFalse(execution_plan["automatic_rollback"])
        self.assertIn("confirm_target_artifact_not_physically_deleted_by_baseline", execution_plan["verification_requirements"])
        self.assertEqual(result.auto_stitch_rollback_execution_summary["execution_plan_count"], 1)
        self.assertEqual(result.auto_stitch_rollback_execution_summary["pending_execution_plan_count"], 1)
        self.assertTrue(result.auto_stitch_rollback_execution_summary["dry_run_only_by_default"])
        self.assertEqual(result.auto_stitch_rollback_execution_results, [])
        self.assertEqual(result.auto_stitch_rollback_execution_result_summary["rollback_execution_result_count"], 0)
        self.assertEqual(len(result.stitched_flows), 1)
        stitched = result.stitched_flows[0]
        self.assertEqual(stitched["stitched_flow_id"], "stitched-flow-1")
        self.assertEqual(stitched["materialization_result_id"], "auto-stitch-materialization-result-1")
        self.assertEqual(stitched["plan_id"], "auto-stitch-materialization-plan-1")
        self.assertTrue(stitched["stitching"])
        self.assertFalse(stitched["automatic_stitching"])
        self.assertEqual(stitched["source"], "review_approved_auto_stitch_materialization_plan")
        result_dict = result.to_dict()
        self.assertEqual(result_dict["auto_stitch_materialization_review_decision_count"], 1)
        self.assertEqual(result_dict["auto_stitch_materialization_result_count"], 1)
        self.assertEqual(result_dict["auto_stitch_materialization_audit_count"], 1)
        self.assertEqual(result_dict["auto_stitch_materialization_rollback_plan_count"], 1)
        self.assertEqual(result_dict["auto_stitch_materialization_transaction_count"], 1)
        self.assertEqual(result_dict["auto_stitch_rollback_execution_plan_count"], 1)
        self.assertEqual(result_dict["auto_stitch_rollback_execution_result_count"], 0)
        self.assertEqual(result_dict["stitched_flow_count"], 1)

    def test_approved_rollback_execution_review_decision_records_logical_revert(self) -> None:
        context = self._ready_flow_context()
        context["auto_stitch_policy"] = {
            "policy_id": "unit-policy",
            "min_confidence_score": 0.85,
            "allow_conflicts": True,
            "enable_automatic_materialization": True,
        }
        context["auto_stitch_materialization_review_decisions"] = [
            {"plan_id": "auto-stitch-materialization-plan-1", "status": "approved", "approved": True, "reviewer": "materialization-reviewer"}
        ]
        context["auto_stitch_rollback_execution_review_decisions"] = [
            {
                "rollback_execution_plan_id": "stitched-flow-rollback-execution-plan-1",
                "status": "approved",
                "approved": True,
                "reviewer": "rollback-reviewer",
                "reviewed_at": "2026-05-31T10:00:00Z",
            }
        ]

        result = FlowTimelineManager().build(FlowTimelineSpec.from_context(context))

        self.assertEqual(len(result.auto_stitch_rollback_execution_review_decisions), 1)
        self.assertEqual(len(result.auto_stitch_rollback_execution_plans), 1)
        execution_plan = result.auto_stitch_rollback_execution_plans[0]
        self.assertEqual(execution_plan["status"], "approved_for_rollback_execution")
        self.assertEqual(execution_plan["execution_mode"], "review_approved_logical_revert_baseline")
        self.assertFalse(execution_plan["review_required"])
        self.assertFalse(execution_plan["dry_run"])
        self.assertTrue(execution_plan["would_revert"])
        self.assertEqual(execution_plan["next_action"], "record_review_approved_rollback_execution_result")
        self.assertEqual(len(result.auto_stitch_rollback_execution_results), 1)
        execution_result = result.auto_stitch_rollback_execution_results[0]
        self.assertEqual(execution_result["status"], "logical_revert_recorded")
        self.assertEqual(execution_result["transaction_id"], "auto-stitch-materialization-txn-1")
        self.assertEqual(execution_result["rollback_execution_plan_id"], "stitched-flow-rollback-execution-plan-1")
        self.assertTrue(execution_result["logical_rollback_recorded"])
        self.assertTrue(execution_result["rollback_executed"])
        self.assertTrue(execution_result["writes_artifact"])
        self.assertTrue(execution_result["would_revert"])
        self.assertFalse(execution_result["physical_artifact_mutated"])
        self.assertFalse(execution_result["target_artifact_mutated"])
        self.assertFalse(execution_result["automatic_rollback"])
        self.assertFalse(execution_result["automatic_stitching"])
        self.assertIn("review_gate_recompute_baseline_does_not_replace_standard_gate", execution_result["limitations"])
        self.assertEqual(result.auto_stitch_rollback_execution_result_summary["rollback_execution_result_count"], 1)
        self.assertEqual(result.auto_stitch_rollback_execution_result_summary["logical_revert_recorded_count"], 1)
        self.assertEqual(result.auto_stitch_rollback_execution_result_summary["approved_review_decision_count"], 1)
        self.assertFalse(result.auto_stitch_rollback_execution_result_summary["physical_artifact_mutated"])
        self.assertEqual(result.auto_stitch_rollback_execution_result_summary["next_action"], "recompute_review_gate_after_rollback_before_delivery")
        self.assertEqual(len(result.auto_stitch_rollback_review_gate_recomputations), 1)
        recomputation = result.auto_stitch_rollback_review_gate_recomputations[0]
        self.assertEqual(recomputation["status"], "post_rollback_review_required")
        self.assertEqual(recomputation["gate_name"], "rollback_after_materialization_review_gate")
        self.assertEqual(recomputation["rollback_execution_result_id"], "stitched-flow-rollback-execution-result-1")
        self.assertEqual(recomputation["transaction_id"], "auto-stitch-materialization-txn-1")
        self.assertEqual(recomputation["review_gate_artifact"], "workspace/review-gate-after-rollback.json")
        self.assertEqual(recomputation["virtual_review_gate_artifact"], "virtual://workspace/review-gate-after-rollback.json")
        self.assertTrue(recomputation["blocked"])
        self.assertTrue(recomputation["review_required"])
        self.assertTrue(recomputation["does_not_replace_review_gate"])
        self.assertFalse(recomputation["delivery_allowed"])
        self.assertFalse(recomputation["physical_artifact_mutated"])
        self.assertFalse(recomputation["target_artifact_mutated"])
        self.assertFalse(recomputation["automatic_rollback"])
        self.assertIn("rerun_standard_review_gate_before_delivery", recomputation["blocking_conditions"])
        self.assertEqual(result.auto_stitch_rollback_review_gate_recomputation_summary["recomputation_count"], 1)
        self.assertEqual(result.auto_stitch_rollback_review_gate_recomputation_summary["blocked_count"], 1)
        self.assertFalse(result.auto_stitch_rollback_review_gate_recomputation_summary["physical_artifact_mutated"])
        self.assertEqual(
            result.auto_stitch_rollback_review_gate_recomputation_summary["next_action"],
            "review_logical_rollback_and_rerun_delivery_gate_before_delivery",
        )
        self.assertEqual(len(result.auto_stitch_physical_rollback_dry_run_diffs), 1)
        dry_run = result.auto_stitch_physical_rollback_dry_run_diffs[0]
        self.assertEqual(dry_run["status"], "physical_rollback_diff_ready_for_review")
        self.assertEqual(dry_run["diff_mode"], "dry_run_only")
        self.assertEqual(dry_run["rollback_execution_result_id"], "stitched-flow-rollback-execution-result-1")
        self.assertEqual(dry_run["review_gate_recomputation_id"], "stitched-flow-rollback-review-gate-recompute-1")
        self.assertEqual(dry_run["diff_artifact"], "workspace/stitched-flow-physical-rollback-diff.json")
        self.assertEqual(dry_run["virtual_diff_artifact"], "virtual://workspace/stitched-flow-physical-rollback-diff.json")
        self.assertTrue(dry_run["dry_run"])
        self.assertTrue(dry_run["review_required"])
        self.assertTrue(dry_run["would_mutate_if_approved"])
        self.assertTrue(dry_run["would_remove_entries"])
        self.assertTrue(dry_run["would_update_manifest"])
        self.assertFalse(dry_run["would_replace_review_gate"])
        self.assertFalse(dry_run["writes_artifact"])
        self.assertFalse(dry_run["physical_artifact_mutated"])
        self.assertFalse(dry_run["target_artifact_mutated"])
        self.assertFalse(dry_run["automatic_rollback"])
        self.assertEqual(dry_run["diff"]["entry_sequences_to_remove"], [1, 2, 3])
        self.assertEqual(dry_run["diff"]["remove_selectors"]["materialization_result_id"], "auto-stitch-materialization-result-1")
        self.assertIn("confirm_no_unrelated_stitched_flow_entries_are_removed", dry_run["verification_requirements"])
        self.assertEqual(result.auto_stitch_physical_rollback_dry_run_diff_summary["dry_run_diff_count"], 1)
        self.assertEqual(result.auto_stitch_physical_rollback_dry_run_diff_summary["would_mutate_if_approved_count"], 1)
        self.assertTrue(result.auto_stitch_physical_rollback_dry_run_diff_summary["dry_run_only"])
        self.assertFalse(result.auto_stitch_physical_rollback_dry_run_diff_summary["physical_artifact_mutated"])
        self.assertEqual(result.auto_stitch_physical_rollback_review_decisions, [])
        self.assertEqual(result.auto_stitch_physical_rollback_results, [])
        self.assertEqual(result.auto_stitch_physical_rollback_result_summary["physical_rollback_result_count"], 0)
        self.assertFalse(result.auto_stitch_physical_rollback_result_summary["target_artifact_mutated"])
        self.assertEqual(result.auto_stitch_post_physical_rollback_review_gate_reruns, [])
        self.assertEqual(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["rerun_count"], 0)
        result_dict = result.to_dict()
        self.assertEqual(result_dict["auto_stitch_rollback_review_gate_recomputation_count"], 1)
        self.assertEqual(result_dict["auto_stitch_rollback_review_gate_recomputation_summary"]["blocked_count"], 1)
        self.assertEqual(result_dict["auto_stitch_physical_rollback_dry_run_diff_count"], 1)
        self.assertEqual(result_dict["auto_stitch_physical_rollback_dry_run_diff_summary"]["dry_run_diff_count"], 1)
        self.assertEqual(result_dict["auto_stitch_physical_rollback_result_count"], 0)
        self.assertEqual(result_dict["auto_stitch_post_physical_rollback_review_gate_rerun_count"], 0)

    def test_approved_physical_rollback_review_decision_mutates_stitched_flow(self) -> None:
        context = self._ready_flow_context()
        context["auto_stitch_policy"] = {
            "policy_id": "unit-policy",
            "min_confidence_score": 0.85,
            "allow_conflicts": True,
            "enable_automatic_materialization": True,
        }
        context["auto_stitch_materialization_review_decisions"] = [
            {"plan_id": "auto-stitch-materialization-plan-1", "status": "approved", "approved": True, "reviewer": "materialization-reviewer"}
        ]
        context["auto_stitch_rollback_execution_review_decisions"] = [
            {
                "rollback_execution_plan_id": "stitched-flow-rollback-execution-plan-1",
                "status": "approved",
                "approved": True,
                "reviewer": "rollback-reviewer",
            }
        ]
        context["auto_stitch_physical_rollback_review_decisions"] = [
            {
                "dry_run_id": "stitched-flow-physical-rollback-diff-1",
                "status": "approved",
                "approved": True,
                "reviewer": "physical-rollback-reviewer",
                "reviewed_at": "2026-05-31T11:00:00Z",
            }
        ]

        result = FlowTimelineManager().build(FlowTimelineSpec.from_context(context))

        self.assertEqual(len(result.auto_stitch_physical_rollback_review_decisions), 1)
        self.assertEqual(len(result.auto_stitch_physical_rollback_dry_run_diffs), 1)
        dry_run = result.auto_stitch_physical_rollback_dry_run_diffs[0]
        self.assertEqual(dry_run["status"], "approved_for_physical_rollback")
        self.assertEqual(dry_run["diff_mode"], "review_approved_physical_rollback")
        self.assertFalse(dry_run["dry_run"])
        self.assertFalse(dry_run["review_required"])
        self.assertTrue(dry_run["writes_artifact"])
        self.assertEqual(dry_run["review_decision"]["review_gate"], "auto_stitch_physical_rollback_review_decision")
        self.assertEqual(result.auto_stitch_physical_rollback_dry_run_diff_summary["approved_for_physical_rollback_count"], 1)
        self.assertFalse(result.auto_stitch_physical_rollback_dry_run_diff_summary["dry_run_only"])

        self.assertEqual(len(result.auto_stitch_physical_rollback_results), 1)
        rollback_result = result.auto_stitch_physical_rollback_results[0]
        self.assertEqual(rollback_result["status"], "physical_rollback_applied")
        self.assertEqual(rollback_result["dry_run_id"], "stitched-flow-physical-rollback-diff-1")
        self.assertEqual(rollback_result["result_artifact"], "workspace/stitched-flow-physical-rollback-results.json")
        self.assertEqual(rollback_result["virtual_result_artifact"], "virtual://workspace/stitched-flow-physical-rollback-results.json")
        self.assertEqual(rollback_result["matched_stitched_flow_ids"], ["stitched-flow-1"])
        self.assertEqual(rollback_result["matched_materialization_result_ids"], ["auto-stitch-materialization-result-1"])
        self.assertEqual(rollback_result["removed_entry_sequences"], [1, 2, 3])
        self.assertTrue(rollback_result["physical_rollback_applied"])
        self.assertTrue(rollback_result["physical_artifact_mutated"])
        self.assertTrue(rollback_result["target_artifact_mutated"])
        self.assertTrue(rollback_result["manifest_update_required"])
        self.assertTrue(rollback_result["standard_review_gate_rerun_required"])
        self.assertFalse(rollback_result["would_replace_review_gate"])
        self.assertFalse(rollback_result["automatic_rollback"])
        self.assertFalse(rollback_result["automatic_stitching"])
        self.assertIn("standard_review_gate_replacement_not_performed", rollback_result["limitations"])

        self.assertEqual(result.stitched_flows, [])
        self.assertEqual(result.auto_stitch_physical_rollback_result_summary["physical_rollback_result_count"], 1)
        self.assertEqual(result.auto_stitch_physical_rollback_result_summary["physical_rollback_applied_count"], 1)
        self.assertTrue(result.auto_stitch_physical_rollback_result_summary["target_artifact_mutated"])
        self.assertTrue(result.auto_stitch_physical_rollback_result_summary["manifest_update_required"])
        self.assertTrue(result.auto_stitch_physical_rollback_result_summary["standard_review_gate_rerun_required"])
        self.assertFalse(result.auto_stitch_physical_rollback_result_summary["would_replace_review_gate"])
        self.assertEqual(
            result.auto_stitch_physical_rollback_result_summary["next_action"],
            "rerun_standard_review_gate_after_physical_rollback",
        )
        self.assertEqual(len(result.auto_stitch_post_physical_rollback_review_gate_reruns), 1)
        gate_rerun = result.auto_stitch_post_physical_rollback_review_gate_reruns[0]
        self.assertEqual(gate_rerun["status"], "standard_review_gate_rerun_required")
        self.assertEqual(gate_rerun["gate_name"], "standard_review_gate_after_physical_rollback")
        self.assertEqual(gate_rerun["physical_rollback_result_id"], "stitched-flow-physical-rollback-result-1")
        self.assertEqual(gate_rerun["review_gate_artifact"], "workspace/review-gate-after-physical-rollback.json")
        self.assertEqual(gate_rerun["virtual_review_gate_artifact"], "virtual://workspace/review-gate-after-physical-rollback.json")
        self.assertEqual(gate_rerun["standard_review_gate_artifact"], "workspace/review-gate.json")
        self.assertEqual(gate_rerun["removed_stitched_flow_ids"], ["stitched-flow-1"])
        self.assertEqual(gate_rerun["remaining_stitched_flow_count"], 0)
        self.assertTrue(gate_rerun["blocked"])
        self.assertTrue(gate_rerun["review_required"])
        self.assertTrue(gate_rerun["does_not_replace_review_gate"])
        self.assertFalse(gate_rerun["delivery_allowed"])
        self.assertFalse(gate_rerun["would_replace_review_gate"])
        self.assertIn("replace_standard_review_gate_after_rerun", gate_rerun["blocking_conditions"])
        self.assertEqual(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["rerun_count"], 1)
        self.assertEqual(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["blocked_count"], 1)
        self.assertTrue(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["target_artifact_mutated"])
        self.assertTrue(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["standard_review_gate_rerun_required"])
        self.assertTrue(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["does_not_replace_review_gate"])
        self.assertFalse(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["would_replace_review_gate"])
        self.assertEqual(
            result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["next_action"],
            "replace_standard_review_gate_after_physical_rollback_rerun",
        )
        self.assertEqual(result.auto_stitch_standard_review_gate_replacement_review_decisions, [])
        self.assertEqual(result.auto_stitch_standard_review_gate_replacement_results, [])
        self.assertEqual(result.auto_stitch_standard_review_gate_replacement_summary["replacement_result_count"], 0)
        self.assertFalse(result.auto_stitch_standard_review_gate_replacement_summary["standard_review_gate_replaced"])
        self.assertEqual(result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns, [])
        self.assertEqual(result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary["rerun_count"], 0)
        self.assertFalse(result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary["delivery_allowed"])
        self.assertEqual(result.auto_stitch_post_standard_review_gate_replacement_final_delivery_packages, [])
        self.assertEqual(result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary["package_count"], 0)
        self.assertFalse(result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary["package_ready"])
        result_dict = result.to_dict()
        self.assertEqual(result_dict["auto_stitch_physical_rollback_review_decision_count"], 1)
        self.assertEqual(result_dict["auto_stitch_physical_rollback_result_count"], 1)
        self.assertEqual(result_dict["auto_stitch_post_physical_rollback_review_gate_rerun_count"], 1)
        self.assertEqual(result_dict["auto_stitch_standard_review_gate_replacement_result_count"], 0)
        self.assertEqual(result_dict["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count"], 0)
        self.assertEqual(result_dict["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count"], 0)
        self.assertEqual(result_dict["stitched_flow_count"], 0)

    def test_approved_standard_review_gate_replacement_records_replacement_result(self) -> None:
        context = self._ready_flow_context()
        context["auto_stitch_policy"] = {
            "policy_id": "unit-policy",
            "min_confidence_score": 0.85,
            "allow_conflicts": True,
            "enable_automatic_materialization": True,
        }
        context["auto_stitch_materialization_review_decisions"] = [
            {"plan_id": "auto-stitch-materialization-plan-1", "status": "approved", "approved": True, "reviewer": "materialization-reviewer"}
        ]
        context["auto_stitch_rollback_execution_review_decisions"] = [
            {"rollback_execution_plan_id": "stitched-flow-rollback-execution-plan-1", "status": "approved", "approved": True}
        ]
        context["auto_stitch_physical_rollback_review_decisions"] = [
            {"dry_run_id": "stitched-flow-physical-rollback-diff-1", "status": "approved", "approved": True}
        ]
        context["auto_stitch_standard_review_gate_replacement_review_decisions"] = [
            {
                "rerun_id": "stitched-flow-post-physical-rollback-review-gate-rerun-1",
                "status": "approved",
                "approved": True,
                "reviewer": "gate-reviewer",
                "reviewed_at": "2026-05-31T12:00:00Z",
            }
        ]

        result = FlowTimelineManager().build(FlowTimelineSpec.from_context(context))

        self.assertEqual(len(result.auto_stitch_standard_review_gate_replacement_review_decisions), 1)
        self.assertEqual(len(result.auto_stitch_post_physical_rollback_review_gate_reruns), 1)
        gate_rerun = result.auto_stitch_post_physical_rollback_review_gate_reruns[0]
        self.assertEqual(gate_rerun["status"], "approved_for_standard_review_gate_replacement")
        self.assertFalse(gate_rerun["review_required"])
        self.assertFalse(gate_rerun["blocked"])
        self.assertFalse(gate_rerun["delivery_allowed"])
        self.assertFalse(gate_rerun["does_not_replace_review_gate"])
        self.assertTrue(gate_rerun["would_replace_review_gate"])
        self.assertEqual(gate_rerun["review_decision"]["review_gate"], "auto_stitch_standard_review_gate_replacement_review_decision")
        self.assertEqual(
            result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["next_action"],
            "record_standard_review_gate_replacement_result",
        )
        self.assertFalse(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["does_not_replace_review_gate"])
        self.assertTrue(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary["would_replace_review_gate"])

        self.assertEqual(len(result.auto_stitch_standard_review_gate_replacement_results), 1)
        replacement = result.auto_stitch_standard_review_gate_replacement_results[0]
        self.assertEqual(replacement["status"], "standard_review_gate_replaced")
        self.assertEqual(replacement["rerun_id"], "stitched-flow-post-physical-rollback-review-gate-rerun-1")
        self.assertEqual(replacement["source_review_gate_artifact"], "workspace/review-gate-after-physical-rollback.json")
        self.assertEqual(replacement["target_review_gate_artifact"], "workspace/review-gate.json")
        self.assertEqual(replacement["replacement_artifact"], "workspace/review-gate-replacement-results.json")
        self.assertEqual(replacement["virtual_replacement_artifact"], "virtual://workspace/review-gate-replacement-results.json")
        self.assertTrue(replacement["standard_review_gate_replaced"])
        self.assertTrue(replacement["review_gate_artifact_mutated"])
        self.assertTrue(replacement["target_artifact_mutated"])
        self.assertTrue(replacement["writes_artifact"])
        self.assertTrue(replacement["delivery_guard_rerun_required"])
        self.assertFalse(replacement["delivery_allowed"])
        self.assertFalse(replacement["automatic_delivery"])
        self.assertFalse(replacement["automatic_rollback"])
        self.assertIn("delivery_guard_rerun_not_performed_by_replacement_baseline", replacement["limitations"])

        self.assertEqual(result.auto_stitch_standard_review_gate_replacement_summary["replacement_result_count"], 1)
        self.assertEqual(result.auto_stitch_standard_review_gate_replacement_summary["standard_review_gate_replaced_count"], 1)
        self.assertTrue(result.auto_stitch_standard_review_gate_replacement_summary["standard_review_gate_replaced"])
        self.assertTrue(result.auto_stitch_standard_review_gate_replacement_summary["review_gate_artifact_mutated"])
        self.assertTrue(result.auto_stitch_standard_review_gate_replacement_summary["delivery_guard_rerun_required"])
        self.assertFalse(result.auto_stitch_standard_review_gate_replacement_summary["delivery_allowed"])
        self.assertFalse(result.auto_stitch_standard_review_gate_replacement_summary["automatic_delivery"])
        self.assertEqual(
            result.auto_stitch_standard_review_gate_replacement_summary["next_action"],
            "rerun_delivery_guard_after_standard_review_gate_replacement",
        )
        self.assertEqual(len(result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns), 1)
        delivery_guard = result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns[0]
        self.assertEqual(delivery_guard["status"], "delivery_guard_rerun_passed")
        self.assertEqual(delivery_guard["guard_name"], "delivery_guard_after_standard_review_gate_replacement")
        self.assertEqual(delivery_guard["replacement_result_id"], "standard-review-gate-replacement-result-1")
        self.assertEqual(delivery_guard["delivery_guard_artifact"], "workspace/delivery-guard-after-review-gate-replacement.json")
        self.assertEqual(
            delivery_guard["virtual_delivery_guard_artifact"],
            "virtual://workspace/delivery-guard-after-review-gate-replacement.json",
        )
        self.assertTrue(delivery_guard["standard_review_gate_replaced"])
        self.assertTrue(delivery_guard["delivery_guard_rerun_performed"])
        self.assertTrue(delivery_guard["delivery_guard_passed"])
        self.assertTrue(delivery_guard["delivery_allowed"])
        self.assertFalse(delivery_guard["automatic_delivery"])
        self.assertTrue(delivery_guard["manual_delivery_required"])
        self.assertFalse(delivery_guard["automatic_rollback"])
        self.assertFalse(delivery_guard["blocked"])
        self.assertIn("does_not_package_final_delivery", delivery_guard["limitations"])
        self.assertEqual(
            delivery_guard["next_action"],
            "manual_delivery_or_package_final_artifacts_after_guard_review",
        )

        delivery_guard_summary = result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary
        self.assertEqual(delivery_guard_summary["rerun_count"], 1)
        self.assertEqual(delivery_guard_summary["source_replacement_result_count"], 1)
        self.assertEqual(delivery_guard_summary["delivery_guard_passed_count"], 1)
        self.assertTrue(delivery_guard_summary["delivery_guard_rerun_performed"])
        self.assertTrue(delivery_guard_summary["delivery_guard_passed"])
        self.assertTrue(delivery_guard_summary["delivery_allowed"])
        self.assertFalse(delivery_guard_summary["automatic_delivery"])
        self.assertTrue(delivery_guard_summary["manual_delivery_required"])
        self.assertEqual(
            delivery_guard_summary["next_action"],
            "manual_delivery_or_package_final_artifacts_after_guard_review",
        )
        self.assertEqual(len(result.auto_stitch_post_standard_review_gate_replacement_final_delivery_packages), 1)
        final_package = result.auto_stitch_post_standard_review_gate_replacement_final_delivery_packages[0]
        self.assertEqual(final_package["status"], "final_delivery_package_ready")
        self.assertEqual(final_package["package_name"], "final_delivery_after_standard_review_gate_replacement")
        self.assertEqual(final_package["delivery_guard_rerun_id"], "standard-review-gate-replacement-delivery-guard-rerun-1")
        self.assertEqual(
            final_package["package_artifact"],
            "workspace/final-delivery-package-after-review-gate-replacement.json",
        )
        self.assertEqual(
            final_package["virtual_package_artifact"],
            "virtual://workspace/final-delivery-package-after-review-gate-replacement.json",
        )
        self.assertIn("workspace/review-gate.json", final_package["included_artifacts"])
        self.assertIn("workspace/review-gate-replacement-results.json", final_package["included_artifacts"])
        self.assertIn("workspace/delivery-guard-after-review-gate-replacement.json", final_package["included_artifacts"])
        self.assertTrue(final_package["package_ready"])
        self.assertTrue(final_package["final_delivery_packaged"])
        self.assertTrue(final_package["delivery_allowed"])
        self.assertTrue(final_package["writes_artifact"])
        self.assertFalse(final_package["automatic_delivery"])
        self.assertTrue(final_package["manual_delivery_required"])
        self.assertFalse(final_package["external_delivery_performed"])
        self.assertFalse(final_package["cross_run_transaction_committed"])
        self.assertFalse(final_package["manifest_revision_committed"])
        self.assertIn("does_not_commit_cross_run_transaction", final_package["limitations"])
        self.assertEqual(
            final_package["next_action"],
            "review_final_delivery_package_and_commit_transaction_or_deliver_manually",
        )

        package_summary = result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary
        self.assertEqual(package_summary["package_count"], 1)
        self.assertEqual(package_summary["source_delivery_guard_rerun_count"], 1)
        self.assertEqual(package_summary["final_delivery_packaged_count"], 1)
        self.assertTrue(package_summary["package_ready"])
        self.assertTrue(package_summary["final_delivery_packaged"])
        self.assertTrue(package_summary["delivery_allowed"])
        self.assertFalse(package_summary["automatic_delivery"])
        self.assertTrue(package_summary["manual_delivery_required"])
        self.assertFalse(package_summary["cross_run_transaction_committed"])
        self.assertEqual(
            package_summary["next_action"],
            "review_final_delivery_package_and_commit_transaction_or_deliver_manually",
        )
        result_dict = result.to_dict()
        self.assertEqual(result_dict["auto_stitch_standard_review_gate_replacement_review_decision_count"], 1)
        self.assertEqual(result_dict["auto_stitch_standard_review_gate_replacement_result_count"], 1)
        self.assertEqual(result_dict["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count"], 1)
        self.assertEqual(result_dict["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count"], 1)

    def test_rejected_auto_stitch_materialization_review_decision_does_not_materialize_plan(self) -> None:
        context = self._ready_flow_context()
        context["auto_stitch_policy"] = {
            "policy_id": "unit-policy",
            "min_confidence_score": 0.85,
            "allow_conflicts": True,
            "enable_automatic_materialization": True,
        }
        context["auto_stitch_materialization_review_decisions"] = [
            {"plan_id": "auto-stitch-materialization-plan-1", "status": "rejected", "reviewer": "materialization-reviewer"}
        ]

        result = FlowTimelineManager().build(FlowTimelineSpec.from_context(context))

        self.assertEqual(len(result.auto_stitch_materialization_plans), 1)
        plan = result.auto_stitch_materialization_plans[0]
        self.assertEqual(plan["status"], "rejected")
        self.assertEqual(plan["review_decision"]["status"], "rejected")
        self.assertIn("materialization_reviewer_rejected", plan["policy_blocking_conditions"])
        self.assertEqual(result.auto_stitch_materialization_results, [])
        self.assertEqual(result.auto_stitch_materialization_result_summary["materialized_count"], 0)
        self.assertFalse(result.auto_stitch_materialization_result_summary["writes_artifact"])
        self.assertEqual(result.auto_stitch_materialization_audit_entries, [])
        self.assertEqual(result.auto_stitch_materialization_audit_summary["audit_count"], 0)
        self.assertEqual(result.auto_stitch_materialization_rollback_plans, [])
        self.assertEqual(result.auto_stitch_materialization_rollback_summary["rollback_plan_count"], 0)
        self.assertEqual(result.auto_stitch_materialization_transactions, [])
        self.assertEqual(result.auto_stitch_materialization_transaction_summary["transaction_count"], 0)
        self.assertEqual(result.stitched_flows, [])

    def test_approved_stitch_review_decision_materializes_stitched_flow(self) -> None:
        context = self._ready_flow_context()
        context["stitch_review_decisions"] = [
            {
                "proposal_id": "stitch-proposal-1",
                "status": "approved",
                "approved": True,
                "reviewer": "unit-reviewer",
                "reviewed_at": "2026-05-30T12:00:00Z",
                "reason": "Initiator, hook, and replay evidence line up.",
            }
        ]
        result = FlowTimelineManager().build(FlowTimelineSpec.from_context(context))

        self.assertEqual(result.stitch_review_decisions[0]["proposal_id"], "stitch-proposal-1")
        self.assertEqual(len(result.stitch_proposals), 1)
        proposal = result.stitch_proposals[0]
        self.assertEqual(proposal["review_decision"]["status"], "approved")
        self.assertTrue(proposal["review_decision"]["approved"])
        self.assertFalse(proposal["review_decision"]["review_required"])
        self.assertEqual(proposal["review_decision"]["reviewer"], "unit-reviewer")
        self.assertEqual(proposal["blocking_conditions"], [])
        self.assertEqual(proposal["next_action"], "materialize_approved_stitched_flow")
        self.assertFalse(proposal["automatic_stitching"])
        self.assertFalse(proposal["stitching"])
        self.assertEqual(len(result.stitched_flows), 1)
        stitched = result.stitched_flows[0]
        self.assertEqual(stitched["stitched_flow_id"], "stitched-flow-1")
        self.assertEqual(stitched["proposal_id"], "stitch-proposal-1")
        self.assertEqual(stitched["status"], "approved")
        self.assertTrue(stitched["stitching"])
        self.assertFalse(stitched["automatic_stitching"])
        self.assertEqual(stitched["scope"], "review-approved-stitch-baseline")
        self.assertEqual(stitched["review_decision"]["reviewer"], "unit-reviewer")
        self.assertIn("review_approved_not_automatically_inferred", stitched["limitations"])
        result_dict = result.to_dict()
        self.assertEqual(result_dict["stitch_review_decision_count"], 1)
        self.assertEqual(result_dict["stitched_flow_count"], 1)
        self.assertEqual(result_dict["stitched_flows"][0]["next_action"], "inspect_stitched_flow_or_use_for_replay_planning")

    def test_rejected_stitch_review_decision_does_not_materialize_stitched_flow(self) -> None:
        context = self._ready_flow_context()
        context["stitch_review_decisions"] = [
            {"proposal_id": "stitch-proposal-1", "status": "rejected", "reviewer": "unit-reviewer"}
        ]
        result = FlowTimelineManager().build(FlowTimelineSpec.from_context(context))

        self.assertEqual(len(result.stitch_proposals), 1)
        proposal = result.stitch_proposals[0]
        self.assertEqual(proposal["review_decision"]["status"], "rejected")
        self.assertFalse(proposal["review_decision"]["approved"])
        self.assertIn("reviewer_rejected", proposal["blocking_conditions"])
        self.assertEqual(result.stitched_flows, [])
        self.assertEqual(result.to_dict()["stitched_flow_count"], 0)

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
        self.assertEqual(result.auto_stitch_dry_runs, [])
        self.assertEqual(result.auto_stitch_policy_decisions, [])
        self.assertEqual(result.auto_stitch_policy_summary["decision_count"], 0)
        self.assertEqual(result.auto_stitch_materialization_plans, [])
        self.assertEqual(result.auto_stitch_materialization_summary["plan_count"], 0)
        self.assertEqual(result.stitch_proposals, [])
        self.assertEqual(result.to_dict()["stitch_candidate_count"], 0)
        self.assertEqual(result.to_dict()["auto_stitch_dry_run_count"], 0)
        self.assertEqual(result.to_dict()["auto_stitch_conflict_resolution_count"], 0)
        self.assertEqual(result.to_dict()["auto_stitch_policy_decision_count"], 0)
        self.assertEqual(result.to_dict()["auto_stitch_materialization_plan_count"], 0)
        self.assertEqual(result.to_dict()["auto_stitch_materialization_transaction_count"], 0)
        self.assertEqual(result.to_dict()["stitch_proposal_count"], 0)


if __name__ == "__main__":
    unittest.main()
