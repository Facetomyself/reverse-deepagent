import hashlib
import json
import unittest

from reverse_deepagent.browser.source_maps import (
    BundlerSymbolScopeManager,
    BundlerSymbolScopeSpec,
    SourceMapFetchManager,
    SourceMapFetchSpec,
    SourceMapLookupManager,
    SourceMapLookupSpec,
    SourceMapConsumerActionPlanManager,
    SourceMapConsumerActionPlanSpec,
    SourceMapConsumerMaterializationManager,
    SourceMapConsumerMaterializationSpec,
    SourceMapDebuggerCandidateReviewManager,
    SourceMapDebuggerCandidateReviewSpec,
    SourceMapDebuggerCandidateSelectionManager,
    SourceMapDebuggerCandidateSelectionSpec,
    SourceMapFollowthroughChainReadinessManager,
    SourceMapFollowthroughChainReadinessSpec,
    SourceMapFollowthroughDispatchApprovalPlanManager,
    SourceMapFollowthroughDispatchApprovalPlanSpec,
    SourceMapFollowthroughDispatchBoundedExecutorGateManager,
    SourceMapFollowthroughDispatchBoundedExecutorGateSpec,
    SourceMapFollowthroughDispatcherApplyPreflightManager,
    SourceMapFollowthroughDispatcherApplyPreflightSpec,
    SourceMapFollowthroughDispatcherHandoffManager,
    SourceMapFollowthroughDispatcherHandoffSpec,
    SourceMapFollowthroughDispatcherManager,
    SourceMapFollowthroughDispatcherResultSpec,
    SourceMapFollowthroughDispatchTransactionPreflightManager,
    SourceMapFollowthroughDispatchTransactionPreflightSpec,
    SourceMapFollowthroughDispatchPreflightManager,
    SourceMapFollowthroughDispatchPreflightSpec,
    SourceMapFollowthroughOneStepPlanManager,
    SourceMapFollowthroughOneStepPlanSpec,
    SourceMapFollowthroughReviewManager,
    SourceMapFollowthroughReviewSpec,
    SourceMapFollowthroughSurfaceSelectionManager,
    SourceMapFollowthroughSurfaceSelectionSpec,
    SourceMapHookCandidateRefinementManager,
    SourceMapHookCandidateRefinementSpec,
    SourceMapHookCandidateSelectionManager,
    SourceMapHookCandidateSelectionSpec,
    SourceMapSelectedExecutorApplicationHandoffManager,
    SourceMapSelectedExecutorApplicationHandoffSpec,
    SourceMapSelectedExecutorResultCheckpointManager,
    SourceMapSelectedExecutorResultCheckpointSpec,
    SourceMapFollowthroughCompletionCheckpointManager,
    SourceMapFollowthroughCompletionCheckpointSpec,
    SourceMapTerminalReviewPackageManager,
    SourceMapTerminalReviewPackageSpec,
    SourceMapTerminalReviewClosureCheckpointManager,
    SourceMapTerminalReviewClosureCheckpointSpec,
    SourceMapTerminalReviewFinalAuditManager,
    SourceMapTerminalReviewFinalAuditSpec,
    SourceMapTerminalReviewActionDecisionManager,
    SourceMapTerminalReviewActionDecisionSpec,
    SourceMapSelectedExecutorApplyPreflightManager,
    SourceMapSelectedExecutorApplyPreflightSpec,
    SourceMapSelectedExecutorApprovalPlanManager,
    SourceMapSelectedExecutorApprovalPlanSpec,
    SourceMapSelectedExecutorInputReviewManager,
    SourceMapSelectedExecutorInputReviewSpec,
    SourceMapTypedPayloadPreflightManager,
    SourceMapTypedPayloadPreflightSpec,
    SourceMapReadinessManager,
    SourceMapReadinessSpec,
    SourceMapSourceContentManager,
    SourceMapSourceContentSpec,
    SourceMapRemapper,
)


BASE64_VLQ_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def encode_vlq_segment(values: list[int]) -> str:
    encoded = []
    for value in values:
        vlq = ((-value) << 1) + 1 if value < 0 else value << 1
        while True:
            digit = vlq & 31
            vlq >>= 5
            if vlq:
                digit |= 32
            encoded.append(BASE64_VLQ_CHARS[digit])
            if not vlq:
                break
    return "".join(encoded)


class SourceMapFetchManagerTests(unittest.TestCase):
    def test_source_map_fetch_plans_same_origin_source_mapping_url_without_network(self) -> None:
        spec = SourceMapFetchSpec.from_context(
            {
                "script_url": "https://example.test/assets/app.js?cache=1",
                "script_source": "console.log('x');\n//# sourceMappingURL=app.js.map?token=secret",
            }
        )

        result = SourceMapFetchManager(fetcher=lambda *_: (_ for _ in ()).throw(AssertionError("network not expected"))).plan_or_fetch(spec)

        self.assertEqual(result.status, "planned")
        self.assertEqual(result.plan["source_map_url"], "https://example.test/assets/app.js.map?token=secret")
        self.assertEqual(result.plan["source_map_url_redacted"], "https://example.test/assets/app.js.map")
        self.assertTrue(result.plan["fetch_allowed"])
        self.assertTrue(result.side_effect_policy["plan_only_by_default"])
        self.assertFalse(result.result["attempted"])

    def test_source_map_fetch_blocks_cross_origin_without_allowlist(self) -> None:
        spec = SourceMapFetchSpec.from_context(
            {
                "script_url": "https://example.test/assets/app.js",
                "source_map_url": "https://cdn.example.test/maps/app.js.map",
                "fetch_source_map": True,
                "review_approved": True,
            }
        )

        result = SourceMapFetchManager(fetcher=lambda *_: b"{}").plan_or_fetch(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "cross_origin_source_map_requires_allowlist_or_override")
        self.assertFalse(result.result["attempted"])

    def test_source_map_fetch_requires_review_before_network(self) -> None:
        spec = SourceMapFetchSpec.from_context(
            {
                "script_url": "https://example.test/assets/app.js",
                "source_map_url": "app.js.map",
                "fetch_source_map": True,
            }
        )

        result = SourceMapFetchManager(fetcher=lambda *_: (_ for _ in ()).throw(AssertionError("network not expected"))).plan_or_fetch(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.result["attempted"])

    def test_source_map_fetches_reviewed_payload_and_indexed_section_urls(self) -> None:
        root_payload = b'{"version":3,"sections":[{"offset":{"line":0,"column":0},"url":"child.map"}]}'
        child_payload = b'{"version":3,"sources":["src/app.js"],"names":["buildSign"],"mappings":"AAAA"}'
        calls: list[str] = []

        def fetcher(url: str, max_bytes: int) -> bytes:
            calls.append(url)
            return child_payload if url.endswith("child.map") else root_payload

        spec = SourceMapFetchSpec.from_context(
            {
                "script_url": "https://example.test/assets/app.js",
                "source_map_url": "app.js.map",
                "fetch_source_map": True,
                "review_approved": True,
                "fetch_indexed_section_urls": True,
            }
        )

        result = SourceMapFetchManager(fetcher=fetcher).plan_or_fetch(spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(calls, ["https://example.test/assets/app.js.map", "https://example.test/assets/child.map"])
        self.assertTrue(result.result["ok"])
        self.assertEqual(result.result["section_count"], 1)
        self.assertEqual(result.result["indexed_section_url_count"], 1)
        self.assertEqual(result.result["indexed_section_success_count"], 1)
        self.assertEqual(result.result["indexed_section_results"][0]["sources_count"], 1)
        self.assertFalse(result.side_effect_policy["browser_cookies_sent"])
        self.assertFalse(result.result["payload_exported"])


class BundlerSymbolScopeManagerTests(unittest.TestCase):
    def test_bundler_symbol_scope_reviews_webpack_symbol_name_candidate_without_side_effects(self) -> None:
        source_map = {
            "version": 3,
            "sourceRoot": "webpack://demo",
            "sources": ["./src/sign.ts"],
            "names": ["buildSign"],
            "mappings": encode_vlq_segment([0, 0, 0, 0, 0]),
        }
        spec = BundlerSymbolScopeSpec.from_context(
            {
                "bundler_symbol_scope": True,
                "script_url": "https://example.test/assets/app.js",
                "script_source": "var __webpack_require__ = {};",
                "source_map": source_map,
                "symbol_name": "buildSign",
                "original_source": "webpack://demo/src/sign.ts",
                "original_line": 0,
                "original_column": 0,
            }
        )

        result = BundlerSymbolScopeManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.bundler-symbol-scope.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertEqual(descriptor["bundler_classification"]["bundler_kind"], "webpack")
        self.assertTrue(descriptor["name_metadata"]["name_present"])
        self.assertEqual(descriptor["name_metadata"]["mapping_name_match_count"], 1)
        self.assertEqual(descriptor["scope_candidate_count"], 1)
        candidate = descriptor["scope_candidates"][0]
        self.assertEqual(candidate["symbol_name"], "buildSign")
        self.assertEqual(candidate["generated_line_number"], 0)
        self.assertEqual(candidate["generated_column_number"], 0)
        self.assertTrue(descriptor["hook_readiness"]["source_logpoint_reviewable"])
        self.assertFalse(descriptor["side_effect_policy"]["fetch_source_map"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["runtime_evaluated"])
        self.assertFalse(descriptor["side_effect_policy"]["logpoint_installed"])
        self.assertFalse(descriptor["side_effect_policy"]["calls_mcp"])
        self.assertFalse(descriptor["side_effect_policy"]["mobile_runtime_used"])

    def test_bundler_symbol_scope_blocks_missing_source_map_payload(self) -> None:
        spec = BundlerSymbolScopeSpec.from_context({"bundler_symbol_scope": True, "symbol_name": "buildSign"})

        result = BundlerSymbolScopeManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "missing_source_map_payload")
        self.assertEqual(result.descriptor["next_action"], "provide_source_map_payload")
        self.assertFalse(result.side_effect_policy["browser_started"])

    def test_bundler_symbol_scope_treats_malformed_source_map_string_as_missing_payload(self) -> None:
        spec = BundlerSymbolScopeSpec.from_context(
            {
                "bundler_symbol_scope": True,
                "source_map": "{not-json",
                "symbol_name": "buildSign",
                "original_source": "./src/sign.ts",
            }
        )

        result = BundlerSymbolScopeManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "missing_source_map_payload")
        self.assertEqual(result.descriptor["blockers"], ["missing_source_map_payload"])
        self.assertFalse(result.descriptor["side_effect_policy"]["fetch_source_map"])


class SourceMapHookCandidateRefinementManagerTests(unittest.TestCase):
    @staticmethod
    def _symbol_scope() -> dict:
        source_map = {
            "version": 3,
            "sourceRoot": "webpack://demo",
            "sources": ["./src/sign.ts"],
            "names": ["buildSign"],
            "mappings": encode_vlq_segment([0, 0, 0, 0, 0]),
        }
        spec = BundlerSymbolScopeSpec.from_context(
            {
                "bundler_symbol_scope": True,
                "script_url": "https://example.test/assets/app.js",
                "script_source": "var __webpack_require__ = {};",
                "source_map": source_map,
                "symbol_name": "buildSign",
                "original_source": "webpack://demo/src/sign.ts",
                "original_line": 0,
                "original_column": 0,
            }
        )
        return BundlerSymbolScopeManager().review(spec).descriptor

    def test_refines_source_map_symbol_scope_into_reviewed_hook_candidates_without_side_effects(self) -> None:
        spec = SourceMapHookCandidateRefinementSpec.from_context(
            {
                "source_map_hook_candidates": True,
                "bundler_symbol_scope": self._symbol_scope(),
                "function_paths": ["window.buildSign"],
                "module_candidates": [{"module_id": "731", "export_names": ["buildSign"], "runtime_path": "window.__webpack_require__"}],
                "source_map_consumer_materialization": {
                    "status": "ready_for_review",
                    "typed_review_payloads": [
                        {"consumer": "hook", "status": "ready_for_review", "payload_kind": "hook-symbol-scope-review"}
                    ],
                    "side_effect_policy": {"hook_installed": False, "browser_started": False, "calls_mcp": False},
                },
            }
        )

        result = SourceMapHookCandidateRefinementManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-hook-candidates.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertEqual(descriptor["requested_symbol"], "buildSign")
        self.assertEqual(descriptor["bundler_kind"], "webpack")
        self.assertEqual(descriptor["source_scope_candidate_count"], 1)
        self.assertEqual(descriptor["candidate_count"], 2)
        self.assertEqual(descriptor["ready_for_hook_install_review_count"], 2)
        self.assertEqual(descriptor["candidate_ranking"]["schema_version"], "reverse-deepagent.source-map-candidate-ranking-summary.v1")
        self.assertTrue(descriptor["candidate_ranking"]["review_only"])
        self.assertTrue(descriptor["candidate_ranking"]["deterministic"])
        self.assertEqual(descriptor["candidate_ranking"]["ranked_candidate_count"], 2)
        kinds = {item["hook_kind"] for item in descriptor["candidates"]}
        self.assertEqual(kinds, {"function", "module"})
        function_candidate = next(item for item in descriptor["candidates"] if item["hook_kind"] == "function")
        self.assertEqual(function_candidate["ranking"]["rank"], 1)
        self.assertGreater(function_candidate["ranking"]["score"], 80)
        self.assertIn("symbol_scope_function_candidate", function_candidate["ranking"]["reasons"])
        self.assertTrue(function_candidate["ranking"]["review_only"])
        self.assertFalse(function_candidate["ranking"]["installs_hook"])
        self.assertFalse(function_candidate["ranking"]["uses_raw_source"])
        self.assertEqual(function_candidate["suggested_hook_install_input"]["function_name"], "buildSign")
        self.assertEqual(function_candidate["suggested_hook_install_input"]["function_paths"], ["window.buildSign"])
        self.assertFalse(function_candidate["suggested_hook_install_input"]["install_supported_now"])
        module_candidate = next(item for item in descriptor["candidates"] if item["hook_kind"] == "module")
        self.assertEqual(module_candidate["suggested_hook_install_input"]["module_id"], "731")
        self.assertEqual(module_candidate["suggested_hook_install_input"]["export_name"], "buildSign")
        self.assertFalse(descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["runtime_evaluated"])
        self.assertFalse(descriptor["side_effect_policy"]["hook_installed"])
        self.assertFalse(descriptor["side_effect_policy"]["automatic_hook_installation"])
        self.assertFalse(descriptor["side_effect_policy"]["calls_mcp"])
        self.assertFalse(descriptor["side_effect_policy"]["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_hook_candidates_before_selected_hook_install")

    def test_blocks_hook_candidate_refinement_without_ready_symbol_scope(self) -> None:
        spec = SourceMapHookCandidateRefinementSpec.from_context(
            {"source_map_hook_candidates": True, "bundler_symbol_scope": {"status": "blocked", "scope_candidates": []}}
        )

        result = SourceMapHookCandidateRefinementManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("bundler_symbol_scope_not_ready", result.descriptor["blockers"])
        self.assertIn("bundler_symbol_scope_has_no_scope_candidates", result.descriptor["blockers"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["hook_installed"])

    def test_hook_candidate_ranking_downgrades_missing_followthrough_signals_without_side_effects(self) -> None:
        spec = SourceMapHookCandidateRefinementSpec.from_context(
            {
                "source_map_hook_candidates": True,
                "bundler_symbol_scope": self._symbol_scope(),
            }
        )

        result = SourceMapHookCandidateRefinementManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["candidate_count"], 1)
        candidate = descriptor["candidates"][0]
        self.assertFalse(candidate["ready_for_hook_install_review"])
        self.assertLess(candidate["ranking"]["score"], 90)
        self.assertIn("review_input_missing", candidate["ranking"]["reasons"])
        self.assertIn("sources_content_metadata_missing", candidate["ranking"]["reasons"])
        self.assertFalse(candidate["ranking"]["signals"]["sources_content_metadata_available"])
        self.assertFalse(descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["hook_installed"])


class SourceMapHookCandidateSelectionManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_hook_candidates() -> dict:
        spec = SourceMapHookCandidateRefinementSpec.from_context(
            {
                "source_map_hook_candidates": True,
                "bundler_symbol_scope": SourceMapHookCandidateRefinementManagerTests._symbol_scope(),
                "function_paths": ["window.buildSign"],
                "module_candidates": [{"module_id": "731", "export_names": ["buildSign"], "runtime_path": "window.__webpack_require__"}],
            }
        )
        return SourceMapHookCandidateRefinementManager().review(spec).descriptor

    def test_selects_hook_candidate_into_selected_executor_input_review_context_without_side_effects(self) -> None:
        candidates = self._ready_hook_candidates()
        selected_id = candidates["candidates"][0]["candidate_id"]
        spec = SourceMapHookCandidateSelectionSpec.from_context(
            {
                "source_map_hook_candidate_selection": True,
                "source_map_hook_candidates": candidates,
                "selected_candidate_id": selected_id,
                "reviewer": "analyst",
            }
        )

        result = SourceMapHookCandidateSelectionManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-hook-candidate-selection.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["selection_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertEqual(descriptor["source_candidates_schema_version"], "reverse-deepagent.source-map-hook-candidates.v1")
        self.assertEqual(descriptor["source_candidates_status"], "ready_for_review")
        self.assertEqual(descriptor["candidate_count"], 2)
        self.assertEqual(descriptor["ready_for_hook_install_review_count"], 2)
        self.assertEqual(descriptor["selected_candidate_id"], selected_id)
        self.assertEqual(descriptor["selected_consumer"], "hook")
        self.assertEqual(descriptor["selected_followthrough_review_surface"], "review_hook_symbol_scope_executor_input")
        self.assertTrue(descriptor["ready_for_selected_executor_input_review"])
        self.assertFalse(descriptor["hook_installed"])
        self.assertFalse(descriptor["automatic_hook_installation"])
        selected_input = descriptor["selected_executor_input"]
        self.assertEqual(selected_input["source_map_hook_candidate_id"], selected_id)
        self.assertEqual(selected_input["hook_install_input"]["function_name"], "buildSign")
        self.assertEqual(selected_input["hook_install_input"]["function_paths"], ["window.buildSign"])
        self.assertFalse(selected_input["hook_install_supported_now"])
        review_context = descriptor["source_map_selected_executor_input_review_context"]
        self.assertEqual(review_context["expected_consumer"], "hook")
        self.assertEqual(review_context["expected_surface"], "review_hook_symbol_scope_executor_input")
        self.assertEqual(review_context["reviewer"], "analyst")
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["hook_installed"])
        self.assertFalse(result.side_effect_policy["automatic_hook_installation"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "run_source_map_selected_executor_input_review_for_selected_hook_candidate")

    def test_blocks_ambiguous_hook_candidate_selection_without_explicit_choice(self) -> None:
        spec = SourceMapHookCandidateSelectionSpec.from_context(
            {
                "source_map_hook_candidate_selection": True,
                "source_map_hook_candidates": self._ready_hook_candidates(),
            }
        )

        result = SourceMapHookCandidateSelectionManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_hook_candidate_selection_ambiguous", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["ready_for_selected_executor_input_review"])
        self.assertEqual(result.descriptor["next_action"], "select_one_source_map_hook_candidate_by_id_or_index")
        self.assertFalse(result.side_effect_policy["hook_installed"])



class SourceMapDebuggerCandidateReviewManagerTests(unittest.TestCase):
    @staticmethod
    def _symbol_scope() -> dict:
        return SourceMapHookCandidateRefinementManagerTests._symbol_scope()

    def test_reviews_source_map_symbol_scope_into_debugger_candidates_without_side_effects(self) -> None:
        spec = SourceMapDebuggerCandidateReviewSpec.from_context(
            {
                "source_map_debugger_candidates": True,
                "script_url": "https://example.test/assets/app.js",
                "bundler_symbol_scope": self._symbol_scope(),
                "source_map_consumer_materialization": {
                    "status": "ready_for_review",
                    "typed_review_payloads": [
                        {"consumer": "debugger", "status": "ready_for_review", "payload_kind": "debugger-location-review"}
                    ],
                    "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False},
                },
            }
        )

        result = SourceMapDebuggerCandidateReviewManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-debugger-candidates.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["candidate_review_only"])
        self.assertEqual(descriptor["requested_symbol"], "buildSign")
        self.assertEqual(descriptor["bundler_kind"], "webpack")
        self.assertEqual(descriptor["source_scope_candidate_count"], 1)
        self.assertEqual(descriptor["candidate_count"], 1)
        self.assertEqual(descriptor["ready_for_debugger_location_review_count"], 1)
        self.assertEqual(descriptor["candidate_ranking"]["schema_version"], "reverse-deepagent.source-map-candidate-ranking-summary.v1")
        self.assertTrue(descriptor["candidate_ranking"]["review_only"])
        self.assertTrue(descriptor["candidate_ranking"]["deterministic"])
        candidate = descriptor["candidates"][0]
        self.assertEqual(candidate["candidate_kind"], "source-map-symbol-generated-location")
        self.assertTrue(candidate["ready_for_debugger_location_review"])
        self.assertEqual(candidate["ranking"]["rank"], 1)
        self.assertGreater(candidate["ranking"]["score"], 70)
        self.assertIn("symbol_scope_generated_location_candidate", candidate["ranking"]["reasons"])
        self.assertFalse(candidate["ranking"]["installs_debugger"])
        self.assertFalse(candidate["ranking"]["uses_raw_source"])
        suggested = candidate["suggested_debugger_location_input"]
        self.assertEqual(suggested["url_pattern"], "https://example.test/assets/app.js")
        self.assertEqual(suggested["line_number"], 0)
        self.assertIsNone(suggested["cdp_command"])
        self.assertFalse(suggested["apply_supported_now"])
        self.assertEqual(descriptor["next_action"], "review_source_map_debugger_candidates_before_selected_debugger_apply")
        self.assertFalse(descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["debugger_execution_performed"])
        self.assertFalse(descriptor["side_effect_policy"]["breakpoint_installed"])
        self.assertFalse(descriptor["side_effect_policy"]["automatic_debugger_continuation"])
        self.assertFalse(descriptor["side_effect_policy"]["calls_mcp"])
        self.assertFalse(descriptor["side_effect_policy"]["mobile_runtime_used"])

    def test_blocks_debugger_candidate_review_without_source_evidence(self) -> None:
        spec = SourceMapDebuggerCandidateReviewSpec.from_context({"source_map_debugger_candidates": True})

        result = SourceMapDebuggerCandidateReviewManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_debugger_candidate_source_evidence_missing", result.descriptor["blockers"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_debugger_candidate_ranking_prefers_lookup_exact_and_remains_stable(self) -> None:
        source_map = {
            "version": 3,
            "sourceRoot": "webpack://demo",
            "sources": ["./src/sign.ts"],
            "sourcesContent": ["export function buildSign(){ return 'x'; }\n"],
            "names": ["buildSign"],
            "mappings": encode_vlq_segment([0, 0, 0, 0, 0]),
        }
        lookup = SourceMapLookupManager().lookup(
            SourceMapLookupSpec.from_context(
                {
                    "source_map_lookup": True,
                    "source_map": source_map,
                    "generated_line": 0,
                    "generated_column": 0,
                }
            )
        ).descriptor
        source_content = SourceMapSourceContentManager().review(
            SourceMapSourceContentSpec.from_context(
                {
                    "source_map_source_content": True,
                    "source_map": source_map,
                    "original_source": "webpack://demo/src/sign.ts",
                    "include_source_preview": True,
                }
            )
        ).descriptor
        context = {
            "source_map_debugger_candidates": True,
            "script_url": "https://example.test/assets/app.js",
            "bundler_symbol_scope": self._symbol_scope(),
            "source_map_lookup": lookup,
            "source_map_source_content": source_content,
            "debugger_location_candidates": [
                {"url_pattern": "https://example.test/assets/app.js", "line_number": 12}
            ],
        }

        first = SourceMapDebuggerCandidateReviewManager().review(SourceMapDebuggerCandidateReviewSpec.from_context(context)).descriptor
        second = SourceMapDebuggerCandidateReviewManager().review(SourceMapDebuggerCandidateReviewSpec.from_context(context)).descriptor

        self.assertEqual(first["candidate_ranking"]["candidate_order"], second["candidate_ranking"]["candidate_order"])
        self.assertEqual(first["candidates"][0]["candidate_kind"], "source-map-lookup-location")
        self.assertEqual(first["candidates"][0]["ranking"]["rank"], 1)
        self.assertIn("source_map_lookup_candidate", first["candidates"][0]["ranking"]["reasons"])
        self.assertIn("sources_content_metadata_available", first["candidates"][0]["ranking"]["reasons"])
        self.assertTrue(first["candidates"][0]["ranking"]["signals"]["lookup_mapping_found"])
        payload = json.dumps(first, sort_keys=True)
        self.assertNotIn("export function buildSign", payload)
        self.assertFalse(first["side_effect_policy"]["browser_started"])
        self.assertFalse(first["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(first["side_effect_policy"]["breakpoint_installed"])

    def test_debugger_candidate_ranking_conservatively_downgrades_missing_signals(self) -> None:
        spec = SourceMapDebuggerCandidateReviewSpec.from_context(
            {
                "source_map_debugger_candidates": True,
                "debugger_location_candidates": [
                    {"url_pattern": "https://example.test/assets/app.js", "line_number": 42}
                ],
            }
        )

        result = SourceMapDebuggerCandidateReviewManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        candidate = result.descriptor["candidates"][0]
        self.assertEqual(candidate["ranking"]["rank"], 1)
        self.assertLess(candidate["ranking"]["score"], 55)
        self.assertEqual(candidate["ranking"]["label"], "low")
        self.assertIn("symbol_name_missing", candidate["ranking"]["reasons"])
        self.assertIn("source_map_lookup_mapping_missing", candidate["ranking"]["reasons"])
        self.assertIn("sources_content_metadata_missing", candidate["ranking"]["reasons"])
        self.assertFalse(candidate["ranking"]["signals"]["lookup_mapping_found"])
        self.assertFalse(candidate["ranking"]["signals"]["sources_content_metadata_available"])
        self.assertFalse(result.descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(result.descriptor["side_effect_policy"]["cdp_command_sent"])


class SourceMapDebuggerCandidateSelectionManagerTests(unittest.TestCase):
    @staticmethod
    def _debugger_candidates() -> dict:
        spec = SourceMapDebuggerCandidateReviewSpec.from_context(
            {
                "source_map_debugger_candidates": True,
                "script_url": "https://example.test/assets/app.js",
                "bundler_symbol_scope": SourceMapDebuggerCandidateReviewManagerTests._symbol_scope(),
            }
        )
        return SourceMapDebuggerCandidateReviewManager().review(spec).descriptor

    def test_selects_debugger_candidate_into_selected_executor_input_review_context_without_side_effects(self) -> None:
        candidates = self._debugger_candidates()
        spec = SourceMapDebuggerCandidateSelectionSpec.from_context(
            {
                "source_map_debugger_candidate_selection": True,
                "source_map_debugger_candidates": candidates,
                "selected_candidate_index": 0,
                "reviewer": "analyst",
            }
        )

        result = SourceMapDebuggerCandidateSelectionManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-debugger-candidate-selection.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["selection_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertEqual(descriptor["source_candidates_schema_version"], "reverse-deepagent.source-map-debugger-candidates.v1")
        self.assertEqual(descriptor["candidate_count"], 1)
        self.assertEqual(descriptor["selected_candidate_index"], 0)
        self.assertTrue(descriptor["ready_for_selected_executor_input_review"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["selected_followthrough_review_surface"], "review_debugger_location_executor_input")
        selected_input = descriptor["selected_executor_input"]
        self.assertEqual(selected_input["location"]["url_pattern"], "https://example.test/assets/app.js")
        self.assertEqual(selected_input["location"]["line_number"], 0)
        self.assertIsNone(selected_input["cdp_command"])
        self.assertTrue(selected_input["requires_review_before_debugger_use"])
        review_context = descriptor["source_map_selected_executor_input_review_context"]
        self.assertEqual(review_context["expected_consumer"], "debugger")
        self.assertEqual(review_context["expected_surface"], "review_debugger_location_executor_input")
        input_review = SourceMapSelectedExecutorInputReviewManager().review(SourceMapSelectedExecutorInputReviewSpec.from_context(review_context))
        self.assertEqual(input_review.status, "ready_for_review")
        self.assertEqual(input_review.descriptor["selected_consumer"], "debugger")
        self.assertEqual(input_review.descriptor["executor_review_package"]["review_gate"]["gate"], "explicit_debugger_location_review")
        self.assertFalse(descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["debugger_execution_performed"])
        self.assertFalse(descriptor["side_effect_policy"]["breakpoint_installed"])
        self.assertFalse(descriptor["side_effect_policy"]["automatic_debugger_continuation"])
        self.assertFalse(descriptor["side_effect_policy"]["calls_mcp"])
        self.assertFalse(descriptor["side_effect_policy"]["mobile_runtime_used"])

    def test_blocks_ambiguous_debugger_candidate_selection_without_explicit_choice(self) -> None:
        candidates = self._debugger_candidates()
        candidates["candidates"].append(dict(candidates["candidates"][0], candidate_id="source-map-debugger:second"))
        candidates["candidate_count"] = 2
        spec = SourceMapDebuggerCandidateSelectionSpec.from_context(
            {
                "source_map_debugger_candidate_selection": True,
                "source_map_debugger_candidates": candidates,
            }
        )

        result = SourceMapDebuggerCandidateSelectionManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_debugger_candidate_selection_ambiguous", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["ready_for_selected_executor_input_review"])
        self.assertEqual(result.descriptor["next_action"], "select_one_source_map_debugger_candidate_by_id_or_index")


class SourceMapLookupManagerTests(unittest.TestCase):
    def test_source_map_lookup_maps_generated_position_to_original_exact_without_side_effects(self) -> None:
        source_map = {
            "version": 3,
            "sourceRoot": "webpack://demo",
            "sources": ["./src/sign.ts"],
            "names": ["buildSign"],
            "mappings": encode_vlq_segment([0, 0, 0, 0, 0]),
        }
        spec = SourceMapLookupSpec.from_context(
            {
                "source_map_lookup": True,
                "source_map": source_map,
                "generated_line": 0,
                "generated_column": 0,
            }
        )

        result = SourceMapLookupManager().lookup(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-lookup.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["mapping_found"])
        self.assertEqual(descriptor["lookup_request"]["lookup_direction"], "generated_to_original")
        location = descriptor["location"]
        self.assertEqual(location["source"], "webpack://demo/./src/sign.ts")
        self.assertEqual(location["original_line_number"], 0)
        self.assertEqual(location["original_column_number"], 0)
        self.assertEqual(location["strategy"], "source_map_generated_exact")
        self.assertEqual(location["metadata"]["name"], "buildSign")
        self.assertFalse(descriptor["side_effect_policy"]["fetch_source_map"])
        self.assertFalse(descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["runtime_evaluated"])
        self.assertFalse(descriptor["side_effect_policy"]["calls_mcp"])
        self.assertFalse(descriptor["side_effect_policy"]["mobile_runtime_used"])

    def test_source_map_lookup_uses_generated_greatest_lower_bound_bias(self) -> None:
        source_map = {
            "version": 3,
            "sources": ["src/sign.ts"],
            "names": [],
            "mappings": f"{encode_vlq_segment([0, 0, 0, 0])},{encode_vlq_segment([10, 0, 0, 5])}",
        }
        spec = SourceMapLookupSpec.from_context(
            {
                "source_map_lookup": True,
                "source_map": source_map,
                "generated_line": 0,
                "generated_column": 12,
            }
        )

        result = SourceMapLookupManager().lookup(spec)

        self.assertEqual(result.status, "ready_for_review")
        location = result.descriptor["location"]
        self.assertEqual(location["line_number"], 0)
        self.assertEqual(location["column_number"], 10)
        self.assertEqual(location["original_column_number"], 5)
        self.assertEqual(location["strategy"], "source_map_generated_bias_glb")
        self.assertEqual(location["metadata"]["matched_generated_column_number"], 10)
        self.assertEqual(location["metadata"]["bias"], "greatest_lower_bound")

    def test_source_map_lookup_maps_indexed_generated_position(self) -> None:
        source_map = {
            "version": 3,
            "sections": [
                {
                    "offset": {"line": 2, "column": 4},
                    "map": {"version": 3, "sources": ["src/sign.ts"], "names": [], "mappings": "AAAA"},
                }
            ],
        }
        spec = SourceMapLookupSpec.from_context(
            {
                "source_map_lookup": True,
                "source_map": source_map,
                "generated_line": 2,
                "generated_column": 4,
            }
        )

        result = SourceMapLookupManager().lookup(spec)

        self.assertEqual(result.status, "ready_for_review")
        location = result.descriptor["location"]
        self.assertEqual(location["line_number"], 2)
        self.assertEqual(location["column_number"], 4)
        self.assertEqual(location["source"], "src/sign.ts")
        self.assertEqual(location["original_line_number"], 0)
        self.assertEqual(location["original_column_number"], 0)
        self.assertEqual(location["strategy"], "source_map_generated_indexed_exact")
        self.assertEqual(location["metadata"]["section_index"], 0)
        self.assertEqual(location["metadata"]["section_offset_line"], 2)
        self.assertEqual(location["metadata"]["section_offset_column"], 4)
        self.assertEqual(location["metadata"]["indexed_section_depth"], 1)

    def test_source_map_lookup_blocks_missing_source_map_payload(self) -> None:
        spec = SourceMapLookupSpec.from_context({"source_map_lookup": True, "generated_line": 0})

        result = SourceMapLookupManager().lookup(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "missing_source_map_payload")
        self.assertEqual(result.descriptor["blockers"], ["missing_source_map_payload"])
        self.assertFalse(result.side_effect_policy["browser_started"])

    def test_source_map_lookup_can_reuse_original_to_generated_remapper(self) -> None:
        source_map = {"version": 3, "sources": ["src/sign.ts"], "names": [], "mappings": "AAAA"}
        spec = SourceMapLookupSpec.from_context(
            {
                "source_map_lookup": True,
                "source_map": source_map,
                "lookup_direction": "original_to_generated",
                "original_source": "src/sign.ts",
                "original_line": 0,
                "original_column": 0,
            }
        )

        result = SourceMapLookupManager().lookup(spec)

        self.assertEqual(result.status, "ready_for_review")
        location = result.descriptor["location"]
        self.assertEqual(location["line_number"], 0)
        self.assertEqual(location["column_number"], 0)
        self.assertEqual(location["source"], "src/sign.ts")
        self.assertEqual(location["strategy"], "source_map_exact")


class SourceMapSourceContentManagerTests(unittest.TestCase):
    def test_source_map_source_content_reviews_flat_sources_content_without_exporting_raw_source(self) -> None:
        content = "export function buildSign(){ return 'x'; }\n"
        source_map = {
            "version": 3,
            "sourceRoot": "webpack://demo",
            "sources": ["./src/sign.ts"],
            "sourcesContent": [content],
            "names": ["buildSign"],
            "mappings": "AAAAA",
        }
        spec = SourceMapSourceContentSpec.from_context(
            {
                "source_map_source_content": True,
                "source_map": source_map,
                "original_source": "webpack://demo/src/sign.ts",
                "include_source_preview": True,
            }
        )

        result = SourceMapSourceContentManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-source-content.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["source_content_available"])
        self.assertEqual(descriptor["source_request"]["original_source"], "webpack://demo/src/sign.ts")
        self.assertFalse(descriptor["source_request"]["raw_source_content_exported"])
        self.assertTrue(descriptor["source_match"]["matched"])
        self.assertEqual(descriptor["source_match"]["resolved_source"], "webpack://demo/./src/sign.ts")
        self.assertNotIn("content", descriptor["source_match"])
        summary = descriptor["content_summary"]
        self.assertTrue(summary["available"])
        self.assertEqual(summary["char_count"], len(content))
        self.assertEqual(summary["byte_count"], len(content.encode("utf-8")))
        self.assertEqual(summary["sha256"], hashlib.sha256(content.encode("utf-8")).hexdigest())
        self.assertTrue(summary["preview_requested"])
        self.assertFalse(summary["preview_exported"])
        self.assertFalse(summary["raw_content_exported"])
        self.assertFalse(descriptor["side_effect_policy"]["raw_source_content_exported"])
        self.assertFalse(descriptor["side_effect_policy"]["preview_exported"])
        self.assertFalse(descriptor["side_effect_policy"]["fetch_source_map"])
        self.assertFalse(descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["runtime_evaluated"])
        self.assertFalse(descriptor["side_effect_policy"]["logpoint_installed"])
        self.assertFalse(descriptor["side_effect_policy"]["calls_mcp"])
        self.assertFalse(descriptor["side_effect_policy"]["mobile_runtime_used"])

    def test_source_map_source_content_reviews_indexed_section_sources_content(self) -> None:
        source_map = {
            "version": 3,
            "sections": [
                {
                    "offset": {"line": 2, "column": 4},
                    "map": {
                        "version": 3,
                        "sources": ["src/sign.ts"],
                        "sourcesContent": ["function sign() { return 1; }"],
                        "names": ["sign"],
                        "mappings": "AAAA",
                    },
                }
            ],
        }
        spec = SourceMapSourceContentSpec.from_context(
            {
                "source_map_source_content": True,
                "source_map": source_map,
                "source_index": 0,
            }
        )

        result = SourceMapSourceContentManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        match = result.descriptor["source_match"]
        self.assertTrue(match["matched"])
        self.assertEqual(match["source"], "src/sign.ts")
        self.assertEqual(match["indexed_section_depth"], 1)
        self.assertEqual(match["section_stack"][0]["section_index"], 0)
        self.assertEqual(result.descriptor["source_map_summary"]["indexed_section_depth"], 1)
        self.assertTrue(result.descriptor["source_content_available"])

    def test_source_map_source_content_blocks_missing_sources_content(self) -> None:
        spec = SourceMapSourceContentSpec.from_context(
            {
                "source_map_source_content": True,
                "source_map": {"version": 3, "sources": ["src/sign.ts"], "names": [], "mappings": "AAAA"},
                "original_source": "src/sign.ts",
            }
        )

        result = SourceMapSourceContentManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_content_missing", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["source_content_available"])
        self.assertEqual(result.descriptor["next_action"], "provide_source_map_with_sources_content")

    def test_source_map_source_content_blocks_missing_source_selector(self) -> None:
        spec = SourceMapSourceContentSpec.from_context(
            {
                "source_map_source_content": True,
                "source_map": {"version": 3, "sources": ["src/sign.ts"], "sourcesContent": ["x"], "mappings": "AAAA"},
            }
        )

        result = SourceMapSourceContentManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("missing_source_selector", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["source_content_available"])

    def test_source_map_source_content_blocks_missing_source_map_payload(self) -> None:
        spec = SourceMapSourceContentSpec.from_context({"source_map_source_content": True, "original_source": "src/sign.ts"})

        result = SourceMapSourceContentManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "missing_source_map_payload")
        self.assertEqual(result.descriptor["blockers"], ["missing_source_map_payload"])
        self.assertFalse(result.side_effect_policy["browser_started"])


class SourceMapReadinessManagerTests(unittest.TestCase):
    def test_source_map_readiness_reviews_joined_lookup_content_and_symbol_descriptors_without_side_effects(self) -> None:
        spec = SourceMapReadinessSpec.from_context(
            {
                "source_map_readiness": True,
                "source_map_lookup": {
                    "status": "ready_for_review",
                    "mapping_found": True,
                    "location": {"strategy": "source_map_generated_exact"},
                    "next_action": "review_source_map_lookup_before_debugger_or_hook_use",
                },
                "source_map_source_content": {
                    "status": "ready_for_review",
                    "source_content_available": True,
                    "content_summary": {"sha256": "abc123", "raw_content_exported": False, "preview_exported": False},
                    "next_action": "review_source_content_availability_before_debugger_or_rebuild",
                },
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "scope_candidate_count": 1,
                    "bundler_classification": {"bundler_kind": "webpack"},
                    "hook_readiness": {"source_logpoint_reviewable": True},
                    "next_action": "review_symbol_scope_before_source_logpoint_or_hook",
                },
                "source_map_fetch_result": {"status": "success", "ok": True, "attempted": True, "payload_exported": False},
            }
        )

        result = SourceMapReadinessManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-readiness.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertEqual(descriptor["blockers"], [])
        readiness = descriptor["readiness"]
        self.assertTrue(readiness["debugger_location_ready"])
        self.assertTrue(readiness["source_content_metadata_ready"])
        self.assertTrue(readiness["source_logpoint_planning_ready"])
        self.assertTrue(readiness["rebuild_source_metadata_ready"])
        self.assertTrue(readiness["bundler_scope_review_ready"])
        self.assertFalse(readiness["raw_source_content_exported"])
        self.assertFalse(readiness["preview_exported"])
        self.assertFalse(readiness["automatic_logpoint_install_supported"])
        self.assertFalse(readiness["automatic_debugger_execution_supported"])
        self.assertFalse(readiness["raw_source_aware_rebuild_supported"])
        self.assertEqual(descriptor["evidence_status"]["source_content"]["sha256"], "abc123")
        self.assertFalse(descriptor["side_effect_policy"]["fetch_source_map"])
        self.assertFalse(descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["runtime_evaluated"])
        self.assertFalse(descriptor["side_effect_policy"]["logpoint_installed"])
        self.assertFalse(descriptor["side_effect_policy"]["calls_mcp"])
        self.assertFalse(descriptor["side_effect_policy"]["mobile_runtime_used"])

    def test_source_map_readiness_blocks_missing_lookup_and_source_content(self) -> None:
        spec = SourceMapReadinessSpec.from_context({"source_map_readiness": True})

        result = SourceMapReadinessManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_lookup_descriptor_missing", result.descriptor["blockers"])
        self.assertIn("source_map_source_content_descriptor_missing", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_ready_source_map_lookup_descriptor")

    def test_source_map_readiness_blocks_raw_source_or_preview_export_leak(self) -> None:
        spec = SourceMapReadinessSpec.from_context(
            {
                "source_map_readiness": True,
                "source_map_lookup": {"status": "ready_for_review", "mapping_found": True},
                "source_map_source_content": {
                    "status": "ready_for_review",
                    "source_content_available": True,
                    "content_summary": {"sha256": "abc123", "raw_content_exported": True, "preview_exported": False},
                },
            }
        )

        result = SourceMapReadinessManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("raw_source_content_export_detected", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "replace_source_content_descriptor_with_metadata_only_version")


class SourceMapConsumerActionPlanManagerTests(unittest.TestCase):
    def test_source_map_consumer_action_plan_reviews_ready_consumers_without_side_effects(self) -> None:
        spec = SourceMapConsumerActionPlanSpec.from_context(
            {
                "source_map_consumer_action_plan": True,
                "source_map_readiness": {
                    "status": "ready_for_review",
                    "readiness": {
                        "debugger_location_ready": True,
                        "source_content_metadata_ready": True,
                        "source_logpoint_planning_ready": True,
                        "rebuild_source_metadata_ready": True,
                        "bundler_scope_review_ready": True,
                        "raw_source_content_exported": False,
                        "preview_exported": False,
                    },
                    "blockers": [],
                    "warnings": [],
                },
                "source_map_lookup": {
                    "status": "ready_for_review",
                    "mapping_found": True,
                    "location": {"strategy": "source_map_generated_exact", "source": "src/sign.ts", "line_number": 0, "column_number": 4},
                },
                "source_map_source_content": {
                    "status": "ready_for_review",
                    "source_content_available": True,
                    "content_summary": {"sha256": "abc123", "raw_content_exported": False, "preview_exported": False},
                },
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "scope_candidate_count": 1,
                    "bundler_classification": {"bundler_kind": "webpack"},
                    "hook_readiness": {"source_logpoint_reviewable": True},
                },
            }
        )

        result = SourceMapConsumerActionPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-consumer-action-plan.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertEqual(descriptor["blockers"], [])
        self.assertEqual(descriptor["action_plan_count"], 4)
        consumers = {item["consumer"] for item in descriptor["action_plans"]}
        self.assertEqual(consumers, {"debugger", "source-logpoint", "rebuild", "hook"})
        self.assertTrue(all(item["review_required"] for item in descriptor["action_plans"]))
        self.assertTrue(all(item["execute_automatically"] is False for item in descriptor["action_plans"]))
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["read_only"])
        self.assertTrue(policy["plan_only"])
        self.assertFalse(policy["fetch_source_map"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["debugger_execution_performed"])
        self.assertFalse(policy["runtime_evaluated"])
        self.assertFalse(policy["logpoint_installed"])
        self.assertFalse(policy["hook_installed"])
        self.assertFalse(policy["rebuild_executed"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_source_map_consumer_action_plan_blocks_missing_readiness(self) -> None:
        spec = SourceMapConsumerActionPlanSpec.from_context({"source_map_consumer_action_plan": True})

        result = SourceMapConsumerActionPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_readiness_descriptor_missing", result.descriptor["blockers"])
        self.assertIn("no_source_map_consumer_action_ready", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_ready_source_map_readiness_descriptor")

    def test_source_map_consumer_action_plan_blocks_raw_source_or_preview_leak(self) -> None:
        spec = SourceMapConsumerActionPlanSpec.from_context(
            {
                "source_map_consumer_action_plan": True,
                "source_map_readiness": {
                    "status": "ready_for_review",
                    "readiness": {
                        "debugger_location_ready": True,
                        "raw_source_content_exported": True,
                        "preview_exported": False,
                    },
                },
            }
        )

        result = SourceMapConsumerActionPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("raw_source_content_export_detected", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "replace_source_content_descriptor_with_metadata_only_version")


class SourceMapConsumerMaterializationManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_action_plan() -> dict:
        plan_spec = SourceMapConsumerActionPlanSpec.from_context(
            {
                "source_map_consumer_action_plan": True,
                "source_map_readiness": {
                    "status": "ready_for_review",
                    "readiness": {
                        "debugger_location_ready": True,
                        "source_content_metadata_ready": True,
                        "source_logpoint_planning_ready": True,
                        "rebuild_source_metadata_ready": True,
                        "bundler_scope_review_ready": True,
                        "raw_source_content_exported": False,
                        "preview_exported": False,
                    },
                    "blockers": [],
                    "warnings": [],
                },
                "source_map_lookup": {
                    "status": "ready_for_review",
                    "mapping_found": True,
                    "location": {"strategy": "source_map_generated_exact", "source": "src/sign.ts", "line_number": 0, "column_number": 4},
                },
                "source_map_source_content": {
                    "status": "ready_for_review",
                    "source_content_available": True,
                    "content_summary": {"sha256": "abc123", "raw_content_exported": False, "preview_exported": False},
                },
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "scope_candidate_count": 1,
                    "bundler_classification": {"bundler_kind": "webpack"},
                    "hook_readiness": {"source_logpoint_reviewable": True},
                },
            }
        )
        return SourceMapConsumerActionPlanManager().review(plan_spec).descriptor

    def test_source_map_consumer_materialization_reviews_payloads_without_side_effects(self) -> None:
        spec = SourceMapConsumerMaterializationSpec.from_context(
            {
                "source_map_consumer_materialization": True,
                "source_map_consumer_action_plan": self._ready_action_plan(),
                "source_map_lookup": {
                    "status": "ready_for_review",
                    "location": {"strategy": "source_map_generated_exact", "source": "src/sign.ts", "line_number": 0, "column_number": 4},
                },
                "source_map_source_content": {
                    "status": "ready_for_review",
                    "content_summary": {"sha256": "abc123", "raw_content_exported": False, "preview_exported": False},
                },
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "scope_candidate_count": 1,
                    "bundler_classification": {"bundler_kind": "webpack"},
                },
            }
        )

        result = SourceMapConsumerMaterializationManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-consumer-materialization.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertEqual(descriptor["blockers"], [])
        self.assertEqual(descriptor["materialization_count"], 4)
        self.assertEqual(descriptor["typed_payload_schema_version"], "reverse-deepagent.source-map-consumer-typed-review-payload.v1")
        self.assertEqual(descriptor["typed_review_payload_count"], 4)
        self.assertEqual(set(descriptor["typed_review_payload_consumers"]), {"debugger", "source-logpoint", "rebuild", "hook"})
        kinds = {item["materialization_kind"] for item in descriptor["materializations"]}
        self.assertEqual(
            kinds,
            {
                "debugger_location_materialization",
                "source_logpoint_materialization",
                "rebuild_source_metadata_materialization",
                "hook_symbol_scope_materialization",
            },
        )
        self.assertTrue(all(item["review_required"] for item in descriptor["materializations"]))
        self.assertTrue(all(item["execute_automatically"] is False for item in descriptor["materializations"]))
        typed_payloads = {item["consumer"]: item["typed_review_payload"] for item in descriptor["materializations"]}
        self.assertEqual(typed_payloads["debugger"]["payload_kind"], "debugger-location-review")
        self.assertEqual(typed_payloads["debugger"]["executor_input"]["location"]["source"], "src/sign.ts")
        self.assertIsNone(typed_payloads["debugger"]["executor_input"]["cdp_command"])
        self.assertEqual(typed_payloads["source-logpoint"]["payload_kind"], "source-logpoint-plan-review")
        self.assertFalse(typed_payloads["source-logpoint"]["executor_input"]["source_logpoint_spec_input"]["install_supported_now"])
        self.assertEqual(typed_payloads["rebuild"]["payload_kind"], "rebuild-source-metadata-review")
        self.assertIsNone(typed_payloads["rebuild"]["executor_input"]["raw_source_content"])
        self.assertEqual(typed_payloads["hook"]["payload_kind"], "hook-symbol-scope-review")
        self.assertTrue(typed_payloads["hook"]["executor_input"]["hook_candidate_review_required"])
        for payload in typed_payloads.values():
            self.assertEqual(payload["schema_version"], "reverse-deepagent.source-map-consumer-typed-review-payload.v1")
            self.assertTrue(payload["review_required"])
            self.assertFalse(payload["execute_automatically"])
            self.assertFalse(payload["safety"]["raw_source_content_exported"])
            self.assertFalse(payload["safety"]["preview_exported"])
            self.assertFalse(payload["safety"]["cdp_command_sent"])
            self.assertFalse(payload["safety"]["debugger_execution_performed"])
            self.assertFalse(payload["safety"]["logpoint_installed"])
            self.assertFalse(payload["safety"]["hook_installed"])
            self.assertFalse(payload["safety"]["rebuild_executed"])
            self.assertFalse(payload["safety"]["calls_mcp"])
            self.assertFalse(payload["safety"]["mobile_runtime_used"])
        rebuild = next(item for item in descriptor["materializations"] if item["consumer"] == "rebuild")
        self.assertEqual(rebuild["rebuild_source_metadata"]["sha256"], "abc123")
        self.assertFalse(rebuild["rebuild_source_metadata"]["raw_content_exported"])
        self.assertFalse(rebuild["rebuild_source_metadata"]["preview_exported"])
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["read_only"])
        self.assertTrue(policy["plan_only"])
        self.assertFalse(policy["fetch_source_map"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["debugger_execution_performed"])
        self.assertFalse(policy["runtime_evaluated"])
        self.assertFalse(policy["logpoint_installed"])
        self.assertFalse(policy["hook_installed"])
        self.assertFalse(policy["rebuild_executed"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_source_map_consumer_materialization_blocks_missing_action_plan(self) -> None:
        spec = SourceMapConsumerMaterializationSpec.from_context({"source_map_consumer_materialization": True})

        result = SourceMapConsumerMaterializationManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_consumer_action_plan_missing", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_ready_source_map_consumer_action_plan_descriptor")

    def test_source_map_consumer_materialization_blocks_raw_source_or_preview_leak(self) -> None:
        action_plan = self._ready_action_plan()
        action_plan["side_effect_policy"]["raw_source_content_exported"] = True
        spec = SourceMapConsumerMaterializationSpec.from_context(
            {
                "source_map_consumer_materialization": True,
                "source_map_consumer_action_plan": action_plan,
            }
        )

        result = SourceMapConsumerMaterializationManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("raw_source_content_export_detected", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "replace_source_content_descriptor_with_metadata_only_version")

    def test_source_map_consumer_materialization_filters_requested_action_ids(self) -> None:
        spec = SourceMapConsumerMaterializationSpec.from_context(
            {
                "source_map_consumer_materialization": True,
                "source_map_consumer_action_plan": self._ready_action_plan(),
                "source_map_materialization_action_ids": ["review-debugger-location-use", "review-rebuild-source-metadata-use"],
            }
        )

        result = SourceMapConsumerMaterializationManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(result.descriptor["materialization_count"], 2)
        self.assertEqual(result.descriptor["typed_review_payload_count"], 2)
        self.assertEqual(result.descriptor["selected_action_ids"], ["review-debugger-location-use", "review-rebuild-source-metadata-use"])
        self.assertEqual(set(result.descriptor["typed_review_payload_consumers"]), {"debugger", "rebuild"})

    def test_source_map_consumer_materialization_blocks_unknown_action_id(self) -> None:
        spec = SourceMapConsumerMaterializationSpec.from_context(
            {
                "source_map_consumer_materialization": True,
                "source_map_consumer_action_plan": self._ready_action_plan(),
                "source_map_materialization_action_ids": ["missing-action"],
            }
        )

        result = SourceMapConsumerMaterializationManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("requested_action_id_not_found:missing-action", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "choose_action_ids_from_source_map_consumer_action_plan")


class SourceMapTypedPayloadPreflightManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_materialization() -> dict:
        spec = SourceMapConsumerMaterializationSpec.from_context(
            {
                "source_map_consumer_materialization": True,
                "source_map_consumer_action_plan": SourceMapConsumerMaterializationManagerTests._ready_action_plan(),
                "source_map_lookup": {
                    "status": "ready_for_review",
                    "location": {"strategy": "source_map_generated_exact", "source": "src/sign.ts", "line_number": 0, "column_number": 4},
                },
                "source_map_source_content": {
                    "status": "ready_for_review",
                    "content_summary": {"sha256": "abc123", "raw_content_exported": False, "preview_exported": False},
                },
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "scope_candidate_count": 1,
                    "bundler_classification": {"bundler_kind": "webpack"},
                },
            }
        )
        return SourceMapConsumerMaterializationManager().review(spec).descriptor

    def test_source_map_typed_payload_preflight_reviews_executor_inputs_without_side_effects(self) -> None:
        materialization = self._ready_materialization()
        spec = SourceMapTypedPayloadPreflightSpec.from_context(
            {
                "source_map_typed_payload_preflight": True,
                "source_map_consumer_materialization": materialization,
            }
        )

        result = SourceMapTypedPayloadPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-typed-payload-preflight.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["preflight_only"])
        self.assertEqual(descriptor["typed_payload_schema_version"], "reverse-deepagent.source-map-consumer-typed-review-payload.v1")
        self.assertEqual(descriptor["source_materialization_status"], "ready_for_review")
        self.assertEqual(descriptor["typed_payload_count"], 4)
        self.assertEqual(descriptor["preflight_payload_count"], 4)
        self.assertTrue(descriptor["ready_for_followthrough_review"])
        self.assertFalse(descriptor["followthrough_executor_invoked"])
        surfaces = {item["consumer"]: item["followthrough_review_surface"] for item in descriptor["preflight_payloads"]}
        self.assertEqual(surfaces["debugger"], "review_debugger_location_executor_input")
        self.assertEqual(surfaces["source-logpoint"], "review_source_logpoint_executor_input")
        self.assertEqual(surfaces["rebuild"], "review_rebuild_source_metadata_executor_input")
        self.assertEqual(surfaces["hook"], "review_hook_symbol_scope_executor_input")
        for item in descriptor["preflight_payloads"]:
            self.assertEqual(item["status"], "ready_for_review")
            self.assertTrue(item["ready_for_followthrough_review"])
            self.assertFalse(item["execute_automatically"])
            self.assertFalse(item["executor_invoked"])
            self.assertFalse(item["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(item["side_effect_policy"]["logpoint_installed"])
            self.assertFalse(item["side_effect_policy"]["hook_installed"])
            self.assertFalse(item["side_effect_policy"]["rebuild_executed"])
            self.assertFalse(item["side_effect_policy"]["calls_mcp"])
            self.assertFalse(item["side_effect_policy"]["mobile_runtime_used"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_typed_payload_preflight_before_explicit_debugger_logpoint_rebuild_or_hook_execution")

    def test_source_map_typed_payload_preflight_filters_requested_consumers(self) -> None:
        materialization = self._ready_materialization()
        spec = SourceMapTypedPayloadPreflightSpec.from_context(
            {
                "source_map_typed_payload_preflight": True,
                "source_map_consumer_materialization": materialization,
                "source_map_typed_payload_consumers": ["debugger", "rebuild"],
            }
        )

        result = SourceMapTypedPayloadPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(result.descriptor["preflight_payload_count"], 2)
        self.assertEqual(result.descriptor["selected_consumers"], ["debugger", "rebuild"])

    def test_source_map_typed_payload_preflight_blocks_unsafe_payload_claims(self) -> None:
        materialization = self._ready_materialization()
        payload = dict(materialization["typed_review_payloads"][0])
        payload["safety"] = dict(payload["safety"])
        payload["safety"]["cdp_command_sent"] = True
        spec = SourceMapTypedPayloadPreflightSpec.from_context(
            {
                "source_map_typed_payload_preflight": True,
                "typed_review_payloads": [payload],
            }
        )

        result = SourceMapTypedPayloadPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("typed_payload_preflight_not_ready:review-debugger-location-use", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["ready_for_followthrough_review"])


class SourceMapFollowthroughReviewManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_preflight() -> dict:
        spec = SourceMapTypedPayloadPreflightSpec.from_context(
            {
                "source_map_typed_payload_preflight": True,
                "source_map_consumer_materialization": SourceMapTypedPayloadPreflightManagerTests._ready_materialization(),
            }
        )
        return SourceMapTypedPayloadPreflightManager().review(spec).descriptor

    def test_source_map_followthrough_review_groups_surfaces_without_side_effects(self) -> None:
        preflight = self._ready_preflight()
        spec = SourceMapFollowthroughReviewSpec.from_context(
            {
                "source_map_followthrough_review": True,
                "source_map_typed_payload_preflight": preflight,
            }
        )

        result = SourceMapFollowthroughReviewManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-review.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertEqual(descriptor["source_preflight_schema_version"], "reverse-deepagent.source-map-typed-payload-preflight.v1")
        self.assertEqual(descriptor["source_preflight_status"], "ready_for_review")
        self.assertEqual(descriptor["typed_payload_schema_version"], "reverse-deepagent.source-map-consumer-typed-review-payload.v1")
        self.assertEqual(descriptor["followthrough_review_count"], 4)
        self.assertEqual(descriptor["ready_followthrough_review_count"], 4)
        self.assertTrue(descriptor["ready_for_explicit_review"])
        self.assertFalse(descriptor["followthrough_executor_invoked"])
        surfaces = {item["consumer"]: item["followthrough_review_surface"] for item in descriptor["followthrough_reviews"]}
        self.assertEqual(surfaces["debugger"], "review_debugger_location_executor_input")
        self.assertEqual(surfaces["source-logpoint"], "review_source_logpoint_executor_input")
        self.assertEqual(surfaces["rebuild"], "review_rebuild_source_metadata_executor_input")
        self.assertEqual(surfaces["hook"], "review_hook_symbol_scope_executor_input")
        prompts = {item["consumer"]: item["review_prompt"] for item in descriptor["followthrough_reviews"]}
        self.assertIn("CDP Debugger command", prompts["debugger"])
        self.assertIn("before installation", prompts["source-logpoint"])
        self.assertIn("digest-only rebuild metadata", prompts["rebuild"])
        self.assertIn("before runtime hook installation", prompts["hook"])
        for item in descriptor["followthrough_reviews"]:
            self.assertEqual(item["status"], "ready_for_review")
            self.assertTrue(item["explicit_review_required"])
            self.assertTrue(item["handoff_only"])
            self.assertFalse(item["execute_automatically"])
            self.assertFalse(item["executor_invoked"])
            self.assertFalse(item["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(item["side_effect_policy"]["logpoint_installed"])
            self.assertFalse(item["side_effect_policy"]["hook_installed"])
            self.assertFalse(item["side_effect_policy"]["rebuild_executed"])
            self.assertFalse(item["side_effect_policy"]["calls_mcp"])
            self.assertFalse(item["side_effect_policy"]["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "choose_explicit_source_map_followthrough_review_surface")
        self.assertFalse(result.side_effect_policy["debugger_execution_performed"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_source_map_followthrough_review_filters_requested_consumers(self) -> None:
        spec = SourceMapFollowthroughReviewSpec.from_context(
            {
                "source_map_followthrough_review": True,
                "source_map_typed_payload_preflight": self._ready_preflight(),
                "source_map_followthrough_consumers": ["debugger", "hook"],
            }
        )

        result = SourceMapFollowthroughReviewManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(result.descriptor["followthrough_review_count"], 2)
        self.assertEqual(result.descriptor["selected_consumers"], ["debugger", "hook"])

    def test_source_map_followthrough_review_blocks_unsafe_preflight(self) -> None:
        preflight = self._ready_preflight()
        preflight["side_effect_policy"] = dict(preflight["side_effect_policy"])
        preflight["side_effect_policy"]["cdp_command_sent"] = True
        spec = SourceMapFollowthroughReviewSpec.from_context(
            {
                "source_map_followthrough_review": True,
                "source_map_typed_payload_preflight": preflight,
            }
        )

        result = SourceMapFollowthroughReviewManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_typed_payload_preflight_cdp_command_detected", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["ready_for_explicit_review"])
        self.assertEqual(result.descriptor["next_action"], "resolve_source_map_typed_payload_preflight_blockers")


class SourceMapFollowthroughSurfaceSelectionManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_followthrough_review() -> dict:
        spec = SourceMapFollowthroughReviewSpec.from_context(
            {
                "source_map_followthrough_review": True,
                "source_map_typed_payload_preflight": SourceMapFollowthroughReviewManagerTests._ready_preflight(),
            }
        )
        return SourceMapFollowthroughReviewManager().review(spec).descriptor

    def test_source_map_followthrough_surface_selection_selects_one_surface_without_side_effects(self) -> None:
        spec = SourceMapFollowthroughSurfaceSelectionSpec.from_context(
            {
                "source_map_followthrough_surface_selection": True,
                "source_map_followthrough_review": self._ready_followthrough_review(),
                "source_map_followthrough_surface_consumers": ["debugger"],
            }
        )

        result = SourceMapFollowthroughSurfaceSelectionManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-surface-selection.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["selection_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertEqual(descriptor["source_followthrough_review_schema_version"], "reverse-deepagent.source-map-followthrough-review.v1")
        self.assertEqual(descriptor["source_followthrough_review_status"], "ready_for_review")
        self.assertEqual(descriptor["candidate_review_count"], 4)
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["selected_action_id"], "review-debugger-location-use")
        self.assertEqual(descriptor["selected_followthrough_review_surface"], "review_debugger_location_executor_input")
        self.assertEqual(descriptor["selected_review"]["payload_kind"], "debugger-location-review")
        self.assertTrue(descriptor["ready_for_surface_review"])
        self.assertFalse(descriptor["surface_executor_invoked"])
        self.assertFalse(descriptor["debugger_executed"])
        self.assertFalse(descriptor["source_logpoint_installed"])
        self.assertFalse(descriptor["hook_installed"])
        self.assertFalse(descriptor["rebuild_executed"])
        self.assertIn("CDP Debugger command", descriptor["downstream_review_prompt"])
        self.assertEqual(descriptor["downstream_next_action"], "review_debugger_location_before_cdp_command")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["surface_executor_invoked"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_debugger_location_before_cdp_command")

    def test_source_map_followthrough_surface_selection_blocks_ambiguous_selection(self) -> None:
        spec = SourceMapFollowthroughSurfaceSelectionSpec.from_context(
            {
                "source_map_followthrough_surface_selection": True,
                "source_map_followthrough_review": self._ready_followthrough_review(),
            }
        )

        result = SourceMapFollowthroughSurfaceSelectionManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_followthrough_surface_selector_missing", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["ready_for_surface_review"])
        self.assertEqual(result.descriptor["next_action"], "choose_one_source_map_followthrough_surface")

    def test_source_map_followthrough_surface_selection_blocks_unsafe_selected_review(self) -> None:
        review = self._ready_followthrough_review()
        selected = next(item for item in review["followthrough_reviews"] if item["consumer"] == "debugger")
        selected["side_effect_policy"] = dict(selected["side_effect_policy"])
        selected["side_effect_policy"]["cdp_command_sent"] = True
        spec = SourceMapFollowthroughSurfaceSelectionSpec.from_context(
            {
                "source_map_followthrough_surface_selection": True,
                "source_map_followthrough_review": review,
                "source_map_followthrough_surface_consumers": ["debugger"],
            }
        )

        result = SourceMapFollowthroughSurfaceSelectionManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("selected_followthrough_review_cdp_command_detected", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["ready_for_surface_review"])
        self.assertEqual(result.descriptor["next_action"], "fix_selected_source_map_followthrough_surface_before_review")


class SourceMapSelectedExecutorInputReviewManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_surface_selection() -> dict:
        spec = SourceMapFollowthroughSurfaceSelectionSpec.from_context(
            {
                "source_map_followthrough_surface_selection": True,
                "source_map_followthrough_review": SourceMapFollowthroughSurfaceSelectionManagerTests._ready_followthrough_review(),
                "source_map_followthrough_surface_consumers": ["debugger"],
            }
        )
        return SourceMapFollowthroughSurfaceSelectionManager().review(spec).descriptor

    @staticmethod
    def _ready_hook_candidate_selection() -> dict:
        candidates = SourceMapHookCandidateSelectionManagerTests._ready_hook_candidates()
        selected_id = candidates["candidates"][0]["candidate_id"]
        spec = SourceMapHookCandidateSelectionSpec.from_context(
            {
                "source_map_hook_candidate_selection": True,
                "source_map_hook_candidates": candidates,
                "selected_candidate_id": selected_id,
                "reviewer": "analyst",
            }
        )
        return SourceMapHookCandidateSelectionManager().review(spec).descriptor

    @staticmethod
    def _ready_debugger_candidate_selection() -> dict:
        candidates = {
            "schema_version": "reverse-deepagent.source-map-debugger-candidates.v1",
            "status": "ready_for_review",
            "candidate_count": 1,
            "ready_for_debugger_location_review_count": 1,
            "review_only": True,
            "plan_only": True,
            "candidates": [
                {
                    "candidate_id": "source-map-debugger:buildSign",
                    "candidate_kind": "source-map-symbol-generated-location",
                    "status": "ready_for_review",
                    "ready_for_debugger_location_review": True,
                    "apply_automatically": False,
                    "suggested_debugger_location_input": {
                        "url_pattern": "https://example.test/assets/app.js",
                        "line_number": 4,
                        "column_number": 0,
                        "source": "webpack://demo/src/sign.ts",
                        "mapping_strategy": "source_map_name",
                        "candidate_id": "source-map-debugger:buildSign",
                        "cdp_command": None,
                        "requires_explicit_review": True,
                    },
                }
            ],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "debugger_execution_performed": False},
        }
        spec = SourceMapDebuggerCandidateSelectionSpec.from_context(
            {
                "source_map_debugger_candidate_selection": True,
                "source_map_debugger_candidates": candidates,
                "selected_candidate_id": "source-map-debugger:buildSign",
                "reviewer": "analyst",
            }
        )
        return SourceMapDebuggerCandidateSelectionManager().review(spec).descriptor

    def test_source_map_selected_executor_input_review_packages_selected_surface_without_side_effects(self) -> None:
        selection = self._ready_surface_selection()
        spec = SourceMapSelectedExecutorInputReviewSpec.from_context(
            {
                "source_map_selected_executor_input_review": True,
                "source_map_followthrough_surface_selection": selection,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapSelectedExecutorInputReviewManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-selected-executor-input-review.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["preflight_only"])
        self.assertTrue(descriptor["executor_input_review_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertEqual(descriptor["source_surface_selection_schema_version"], "reverse-deepagent.source-map-followthrough-surface-selection.v1")
        self.assertEqual(descriptor["source_surface_selection_status"], "ready_for_review")
        self.assertEqual(descriptor["selected_action_id"], "review-debugger-location-use")
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["selected_followthrough_review_surface"], "review_debugger_location_executor_input")
        self.assertTrue(descriptor["executor_review_package_ready"])
        self.assertTrue(descriptor["ready_for_executor_review"])
        package = descriptor["executor_review_package"]
        self.assertEqual(package["package_version"], "reverse-deepagent.source-map-selected-executor-input-review.package.v1")
        self.assertEqual(package["review_gate"]["gate"], "explicit_debugger_location_review")
        self.assertEqual(package["review_gate"]["required_approval_flag"], "review_approved")
        self.assertFalse(package["execute_automatically"])
        self.assertFalse(package["executor_invoked"])
        self.assertFalse(descriptor["surface_executor_invoked"])
        self.assertFalse(descriptor["debugger_executed"])
        self.assertFalse(descriptor["source_logpoint_installed"])
        self.assertFalse(descriptor["hook_installed"])
        self.assertFalse(descriptor["rebuild_executed"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["surface_executor_invoked"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_debugger_location_before_cdp_command")

    def test_source_map_selected_executor_input_review_consumes_debugger_candidate_selection_handoff(self) -> None:
        candidate_selection = self._ready_debugger_candidate_selection()
        spec = SourceMapSelectedExecutorInputReviewSpec.from_context(
            {
                "source_map_debugger_candidate_selected_input_review": True,
                "source_map_debugger_candidate_selection": candidate_selection,
            }
        )

        result = SourceMapSelectedExecutorInputReviewManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-selected-executor-input-review.v1")
        self.assertEqual(descriptor["source_debugger_candidate_selection_schema_version"], "reverse-deepagent.source-map-debugger-candidate-selection.v1")
        self.assertEqual(descriptor["source_debugger_candidate_selection_status"], "ready_for_review")
        self.assertEqual(descriptor["source_debugger_candidate_selection_id"], "source-map-debugger:buildSign")
        self.assertTrue(descriptor["source_debugger_candidate_selection_ready"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["selected_followthrough_review_surface"], "review_debugger_location_executor_input")
        self.assertEqual(descriptor["expected_consumer"], "debugger")
        self.assertEqual(descriptor["reviewer"], "analyst")
        self.assertTrue(descriptor["executor_review_package_ready"])
        self.assertTrue(descriptor["ready_for_executor_review"])
        self.assertIn("selected_executor_input_review_from_debugger_candidate_selection", descriptor["warnings"])
        package = descriptor["executor_review_package"]
        self.assertEqual(package["review_gate"]["gate"], "explicit_debugger_location_review")
        self.assertFalse(package["execute_automatically"])
        self.assertFalse(package["executor_invoked"])
        self.assertFalse(descriptor["debugger_executed"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_debugger_location_before_cdp_command")

    def test_source_map_selected_executor_input_review_consumes_hook_candidate_selection_handoff(self) -> None:
        candidate_selection = self._ready_hook_candidate_selection()
        spec = SourceMapSelectedExecutorInputReviewSpec.from_context(
            {
                "source_map_hook_candidate_selected_executor_input_review": True,
                "source_map_hook_candidate_selection": candidate_selection,
            }
        )

        result = SourceMapSelectedExecutorInputReviewManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-selected-executor-input-review.v1")
        self.assertEqual(descriptor["source_hook_candidate_selection_schema_version"], "reverse-deepagent.source-map-hook-candidate-selection.v1")
        self.assertEqual(descriptor["source_hook_candidate_selection_status"], "ready_for_review")
        self.assertEqual(descriptor["source_hook_candidate_selection_id"], candidate_selection["selected_candidate_id"])
        self.assertTrue(descriptor["source_hook_candidate_selection_ready"])
        self.assertEqual(descriptor["selected_consumer"], "hook")
        self.assertEqual(descriptor["selected_followthrough_review_surface"], "review_hook_symbol_scope_executor_input")
        self.assertEqual(descriptor["expected_consumer"], "hook")
        self.assertEqual(descriptor["reviewer"], "analyst")
        self.assertTrue(descriptor["executor_review_package_ready"])
        self.assertTrue(descriptor["ready_for_executor_review"])
        self.assertIn("selected_executor_input_review_from_hook_candidate_selection", descriptor["warnings"])
        package = descriptor["executor_review_package"]
        self.assertEqual(package["review_gate"]["gate"], "explicit_hook_symbol_scope_review")
        self.assertFalse(package["execute_automatically"])
        self.assertFalse(package["executor_invoked"])
        self.assertFalse(descriptor["hook_installed"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_hook_symbol_scope_before_runtime_hook")

    def test_source_map_selected_executor_input_review_blocks_unready_selection(self) -> None:
        selection = self._ready_surface_selection()
        selection["status"] = "blocked"
        selection["ready_for_surface_review"] = False
        spec = SourceMapSelectedExecutorInputReviewSpec.from_context(
            {
                "source_map_selected_executor_input_review": True,
                "source_map_followthrough_surface_selection": selection,
            }
        )

        result = SourceMapSelectedExecutorInputReviewManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_followthrough_surface_selection_not_ready", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["ready_for_executor_review"])
        self.assertEqual(result.descriptor["next_action"], "resolve_source_map_followthrough_surface_selection_blockers")

    def test_source_map_selected_executor_input_review_blocks_executor_input_mismatch(self) -> None:
        selection = self._ready_surface_selection()
        spec = SourceMapSelectedExecutorInputReviewSpec.from_context(
            {
                "source_map_selected_executor_input_review": True,
                "source_map_followthrough_surface_selection": selection,
                "selected_executor_input": {"unexpected": True},
            }
        )

        result = SourceMapSelectedExecutorInputReviewManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("selected_executor_input_mismatch", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["executor_review_package_ready"])


class SourceMapSelectedExecutorApprovalPlanManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_input_review() -> dict:
        selection = SourceMapSelectedExecutorInputReviewManagerTests._ready_surface_selection()
        spec = SourceMapSelectedExecutorInputReviewSpec.from_context(
            {
                "source_map_selected_executor_input_review": True,
                "source_map_followthrough_surface_selection": selection,
                "expected_consumer": "debugger",
            }
        )
        return SourceMapSelectedExecutorInputReviewManager().review(spec).descriptor

    def test_source_map_selected_executor_approval_plan_reviews_apply_contract_without_side_effects(self) -> None:
        input_review = self._ready_input_review()
        spec = SourceMapSelectedExecutorApprovalPlanSpec.from_context(
            {
                "source_map_selected_executor_approval_plan": True,
                "source_map_selected_executor_input_review": input_review,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapSelectedExecutorApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-selected-executor-approval-plan.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["approval_plan_only"])
        self.assertTrue(descriptor["apply_plan_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertEqual(descriptor["source_executor_input_review_schema_version"], "reverse-deepagent.source-map-selected-executor-input-review.v1")
        self.assertEqual(descriptor["source_executor_input_review_status"], "ready_for_review")
        self.assertEqual(descriptor["selected_action_id"], "review-debugger-location-use")
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["selected_review_gate"], "explicit_debugger_location_review")
        self.assertTrue(descriptor["approval_plan_ready"])
        self.assertTrue(descriptor["apply_plan_ready_for_review"])
        self.assertFalse(descriptor["approval_recorded"])
        self.assertFalse(descriptor["ready_to_apply_now"])
        self.assertFalse(descriptor["surface_executor_invoked"])
        approval = descriptor["approval_requirements"]
        self.assertEqual(approval["approval_schema_version"], "reverse-deepagent.source-map-selected-executor-approval.v1")
        self.assertEqual(approval["approval_record_artifact"], "workspace/source-map-selected-executor-approval-record.json")
        self.assertEqual(approval["approval_scope"]["consumer"], "debugger")
        apply_plan = descriptor["apply_plan"]
        self.assertEqual(apply_plan["apply_plan_schema_version"], "reverse-deepagent.source-map-selected-executor-apply-plan.v1")
        self.assertEqual(apply_plan["future_action"], "execute_reviewed_source_map_debugger_location_action")
        self.assertEqual(apply_plan["future_result_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertFalse(apply_plan["ready_to_apply_now"])
        self.assertFalse(apply_plan["executor_implemented_now"])
        self.assertFalse(apply_plan["surface_executor_invoked"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["logpoint_installed"])
        self.assertFalse(result.side_effect_policy["hook_installed"])
        self.assertFalse(result.side_effect_policy["rebuild_executed"])
        self.assertFalse(result.side_effect_policy["surface_executor_invoked"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "record_review_approval_for_source_map_debugger_executor")

    def test_source_map_selected_executor_approval_plan_blocks_unready_input_review(self) -> None:
        input_review = self._ready_input_review()
        input_review["status"] = "blocked"
        input_review["ready_for_executor_review"] = False
        spec = SourceMapSelectedExecutorApprovalPlanSpec.from_context(
            {
                "source_map_selected_executor_approval_plan": True,
                "source_map_selected_executor_input_review": input_review,
            }
        )

        result = SourceMapSelectedExecutorApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_selected_executor_input_review_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_input_review_not_ready_for_approval_plan", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["approval_plan_ready"])
        self.assertEqual(result.descriptor["next_action"], "resolve_source_map_selected_executor_input_review_blockers")

    def test_source_map_selected_executor_approval_plan_blocks_gate_mismatch(self) -> None:
        input_review = self._ready_input_review()
        spec = SourceMapSelectedExecutorApprovalPlanSpec.from_context(
            {
                "source_map_selected_executor_approval_plan": True,
                "source_map_selected_executor_input_review": input_review,
                "expected_gate": "wrong",
            }
        )

        result = SourceMapSelectedExecutorApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("selected_review_gate_mismatch", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["apply_plan_ready_for_review"])


class SourceMapSelectedExecutorApplyPreflightManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_approval_plan() -> dict:
        input_review = SourceMapSelectedExecutorApprovalPlanManagerTests._ready_input_review()
        spec = SourceMapSelectedExecutorApprovalPlanSpec.from_context(
            {
                "source_map_selected_executor_approval_plan": True,
                "source_map_selected_executor_input_review": input_review,
                "expected_consumer": "debugger",
            }
        )
        return SourceMapSelectedExecutorApprovalPlanManager().review(spec).descriptor

    @staticmethod
    def _approval_record(approval_plan: dict, *, digest: str | None = None, status: str = "written", approved: bool = True) -> dict:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-approval-record.v1",
            "status": status,
            "approval_recorded": status == "written",
            "approved_for_apply": approved,
            "approval_record_id": "source-map-selected-executor-approval-record:test",
            "selected_action_id": approval_plan["selected_action_id"],
            "selected_consumer": approval_plan["selected_consumer"],
            "selected_review_gate": approval_plan["selected_review_gate"],
            "decision": "approved" if approved else "rejected",
            "reviewer": "reviewer-1",
            "approval_plan_digest_sha256": digest if digest is not None else hashlib.sha256(json.dumps(approval_plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(),
            "blockers": [],
            "executor_input_gates": {
                "approval_recorded": status == "written",
                "approved_for_apply": approved,
                "ready_to_apply_now": False,
                "surface_executor_invoked": False,
                "requires_apply_preflight_followup": True,
            },
            "side_effect_policy": {
                "read_only": False,
                "review_only": False,
                "approval_record_writer_only": True,
                "files_mutated": status == "written",
                "approval_recorded": status == "written",
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "surface_executor_invoked": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    @staticmethod
    def _dispatcher_result(approval_plan: dict, **overrides: object) -> dict:
        apply_plan = approval_plan.get("apply_plan") if isinstance(approval_plan.get("apply_plan"), dict) else {}
        payload = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-result.v1",
            "status": "dispatched",
            "dispatcher_result_id": "source-map-dispatcher-result:test",
            "selected_consumer": approval_plan["selected_consumer"],
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": apply_plan.get("future_result_artifact", "workspace/source-map-debugger-execution-result.json"),
            "dispatcher_decision_recorded": True,
            "requires_selected_executor_apply_preflight": True,
            "dispatcher_mvp_invoked": True,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "runtime_apply_preflight_invoked": False,
            "ready_to_execute_selected_executor_now": False,
            "blockers": [],
            "side_effect_policy": {
                "dispatcher_decision_recorded": True,
                "dispatcher_mvp_invoked": True,
                "dispatcher_invoked": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "selected_executor_invoked": False,
                "selected_executor_apply_preflight_invoked": False,
                "runtime_apply_preflight_invoked": False,
                "ready_to_dispatch_now": False,
                "ready_to_execute_now": False,
                "ready_to_execute_selected_executor_now": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        payload.update(overrides)
        return payload

    def test_source_map_selected_executor_apply_preflight_reviews_approved_record_without_side_effects(self) -> None:
        approval_plan = self._ready_approval_plan()
        approval_record = self._approval_record(approval_plan)
        spec = SourceMapSelectedExecutorApplyPreflightSpec.from_context(
            {
                "source_map_selected_executor_apply_preflight": True,
                "source_map_selected_executor_approval_plan": approval_plan,
                "source_map_selected_executor_approval_record": approval_record,
                "expected_consumer": "debugger",
                "expected_gate": "explicit_debugger_location_review",
            }
        )

        result = SourceMapSelectedExecutorApplyPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-selected-executor-apply-preflight.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["preflight_only"])
        self.assertTrue(descriptor["apply_preflight_only"])
        self.assertEqual(descriptor["source_approval_plan_schema_version"], "reverse-deepagent.source-map-selected-executor-approval-plan.v1")
        self.assertEqual(descriptor["source_approval_record_schema_version"], "reverse-deepagent.source-map-selected-executor-approval-record.v1")
        self.assertEqual(descriptor["selected_action_id"], "review-debugger-location-use")
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["selected_review_gate"], "explicit_debugger_location_review")
        self.assertEqual(descriptor["approval_record_id"], "source-map-selected-executor-approval-record:test")
        self.assertTrue(descriptor["approval_record_verified"])
        self.assertTrue(descriptor["executor_input_ready"])
        self.assertTrue(descriptor["ready_for_selected_executor_review"])
        self.assertFalse(descriptor["ready_to_apply_now"])
        self.assertFalse(descriptor["future_executor_contract"]["implemented"])
        self.assertEqual(descriptor["future_action"], "execute_reviewed_source_map_debugger_location_action")
        self.assertEqual(descriptor["next_action"], "review_source_map_debugger_executor_application")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["logpoint_installed"])
        self.assertFalse(result.side_effect_policy["hook_installed"])
        self.assertFalse(result.side_effect_policy["rebuild_executed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_source_map_selected_executor_apply_preflight_accepts_dispatcher_result_handoff_without_execution(self) -> None:
        approval_plan = self._ready_approval_plan()
        approval_record = self._approval_record(approval_plan)
        dispatcher_result = self._dispatcher_result(approval_plan)
        dispatcher_digest = hashlib.sha256(json.dumps(dispatcher_result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapSelectedExecutorApplyPreflightSpec.from_context(
            {
                "source_map_selected_executor_apply_preflight": True,
                "source_map_selected_executor_approval_plan": approval_plan,
                "source_map_selected_executor_approval_record": approval_record,
                "source_map_followthrough_dispatcher_result": dispatcher_result,
                "expected_consumer": "debugger",
                "expected_gate": "explicit_debugger_location_review",
                "expected_dispatcher_result_id": "source-map-dispatcher-result:test",
                "expected_dispatcher_result_digest_sha256": dispatcher_digest,
            }
        )

        result = SourceMapSelectedExecutorApplyPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-selected-executor-apply-preflight.v1")
        self.assertTrue(descriptor["dispatcher_result_verified"])
        self.assertFalse(descriptor["dispatcher_result_optional"])
        self.assertTrue(descriptor["dispatcher_decision_recorded"])
        self.assertEqual(descriptor["source_dispatcher_result_schema_version"], "reverse-deepagent.source-map-followthrough-dispatcher-result.v1")
        self.assertEqual(descriptor["source_dispatcher_result_status"], "dispatched")
        self.assertEqual(descriptor["source_dispatcher_result_digest_sha256"], dispatcher_digest)
        self.assertEqual(descriptor["dispatcher_result_id"], "source-map-dispatcher-result:test")
        self.assertTrue(descriptor["dispatcher_result_handoff_only"])
        self.assertFalse(descriptor["dispatcher_result_selected_executor_invoked"])
        self.assertFalse(descriptor["dispatcher_result_selected_executor_apply_preflight_invoked"])
        self.assertFalse(descriptor["dispatcher_result_dispatch_target_invoked"])
        self.assertTrue(descriptor["dispatcher_result_handoff"]["dispatcher_result_verified"])
        self.assertEqual(descriptor["dispatcher_result_handoff"]["selected_executor_apply_preflight_artifact"], "workspace/source-map-selected-executor-apply-preflight.json")
        self.assertTrue(descriptor["ready_for_selected_executor_review"])
        self.assertFalse(descriptor["ready_to_apply_now"])
        self.assertFalse(descriptor["surface_executor_invoked"])
        self.assertFalse(descriptor["future_executor_contract"]["implemented"])
        self.assertEqual(descriptor["next_action"], "review_source_map_debugger_executor_application")
        self.assertIn("source_map_followthrough_dispatcher_result_handoff_does_not_execute_selected_executor", descriptor["warnings"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_source_map_selected_executor_apply_preflight_blocks_bad_dispatcher_result_handoff(self) -> None:
        approval_plan = self._ready_approval_plan()
        approval_record = self._approval_record(approval_plan)
        dispatcher_result = self._dispatcher_result(
            approval_plan,
            selected_consumer="hook",
            selected_executor_invoked=True,
            side_effect_policy={
                "selected_executor_invoked": True,
                "browser_started": True,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        )
        spec = SourceMapSelectedExecutorApplyPreflightSpec.from_context(
            {
                "source_map_selected_executor_apply_preflight": True,
                "source_map_selected_executor_approval_plan": approval_plan,
                "source_map_selected_executor_approval_record": approval_record,
                "source_map_followthrough_dispatcher_result": dispatcher_result,
            }
        )

        result = SourceMapSelectedExecutorApplyPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["dispatcher_result_verified"])
        self.assertIn("source_map_followthrough_dispatcher_result_consumer_mismatch", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_dispatcher_result_selected_executor_already_invoked", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_dispatcher_result_side_effect_detected", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "resolve_source_map_followthrough_dispatcher_result_handoff_blockers")

    def test_source_map_selected_executor_apply_preflight_blocks_missing_approval_record(self) -> None:
        approval_plan = self._ready_approval_plan()
        spec = SourceMapSelectedExecutorApplyPreflightSpec.from_context(
            {
                "source_map_selected_executor_apply_preflight": True,
                "source_map_selected_executor_approval_plan": approval_plan,
            }
        )

        result = SourceMapSelectedExecutorApplyPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_selected_executor_approval_record_missing", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_source_map_selected_executor_approval_plan_and_record")

    def test_source_map_selected_executor_apply_preflight_blocks_digest_mismatch(self) -> None:
        approval_plan = self._ready_approval_plan()
        approval_record = self._approval_record(approval_plan, digest="bad-digest")
        spec = SourceMapSelectedExecutorApplyPreflightSpec.from_context(
            {
                "source_map_selected_executor_apply_preflight": True,
                "source_map_selected_executor_approval_plan": approval_plan,
                "source_map_selected_executor_approval_record": approval_record,
            }
        )

        result = SourceMapSelectedExecutorApplyPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("approval_record_plan_digest_mismatch", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "record_or_refresh_source_map_selected_executor_approval")


class SourceMapSelectedExecutorApplicationHandoffManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_apply_preflight() -> dict:
        approval_plan = SourceMapSelectedExecutorApplyPreflightManagerTests._ready_approval_plan()
        approval_record = SourceMapSelectedExecutorApplyPreflightManagerTests._approval_record(approval_plan)
        spec = SourceMapSelectedExecutorApplyPreflightSpec.from_context(
            {
                "source_map_selected_executor_apply_preflight": True,
                "source_map_selected_executor_approval_plan": approval_plan,
                "source_map_selected_executor_approval_record": approval_record,
                "expected_consumer": "debugger",
            }
        )
        return SourceMapSelectedExecutorApplyPreflightManager().review(spec).descriptor

    def test_source_map_selected_executor_application_handoff_reviews_ready_apply_preflight_without_execution(self) -> None:
        apply_preflight = self._ready_apply_preflight()
        apply_preflight_digest = hashlib.sha256(json.dumps(apply_preflight, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapSelectedExecutorApplicationHandoffSpec.from_context(
            {
                "source_map_selected_executor_application_handoff": True,
                "source_map_selected_executor_apply_preflight": apply_preflight,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
                "expected_apply_preflight_digest_sha256": apply_preflight_digest,
                "reviewer": "analyst",
            }
        )

        result = SourceMapSelectedExecutorApplicationHandoffManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-selected-executor-application-handoff.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertTrue(descriptor["application_handoff_only"])
        self.assertEqual(descriptor["source_apply_preflight_schema_version"], "reverse-deepagent.source-map-selected-executor-apply-preflight.v1")
        self.assertEqual(descriptor["source_apply_preflight_status"], "ready_for_review")
        self.assertEqual(descriptor["source_apply_preflight_digest_sha256"], apply_preflight_digest)
        self.assertEqual(descriptor["selected_action_id"], "review-debugger-location-use")
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["selected_review_gate"], "explicit_debugger_location_review")
        self.assertTrue(descriptor["approval_record_verified"])
        self.assertTrue(descriptor["executor_input_ready"])
        self.assertTrue(descriptor["ready_for_selected_executor_review"])
        self.assertTrue(descriptor["ready_for_application_review"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertEqual(descriptor["application_surface"], "source-map-debugger-application")
        self.assertEqual(descriptor["application_input_key"], "source_map_debugger_location_input")
        self.assertEqual(descriptor["required_approval_flags"], ["review_approved", "approve_source_map_debugger_action"])
        self.assertEqual(descriptor["future_result_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertEqual(descriptor["next_action"], "review_source_map_debugger_executor_application")
        review_input = descriptor["application_review_input"]
        self.assertEqual(review_input["schema_version"], "reverse-deepagent.source-map-selected-executor-application-review-input.v1")
        self.assertEqual(review_input["application_surface"], "source-map-debugger-application")
        self.assertEqual(review_input["apply_preflight_digest_sha256"], apply_preflight_digest)
        self.assertFalse(review_input["execute_automatically"])
        self.assertFalse(review_input["ready_to_execute_now"])
        self.assertFalse(descriptor["surface_executor_invoked"])
        self.assertFalse(descriptor["application_invoked"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_source_map_selected_executor_application_handoff_blocks_bad_apply_preflight(self) -> None:
        apply_preflight = self._ready_apply_preflight()
        apply_preflight["selected_consumer"] = "hook"
        apply_preflight["surface_executor_invoked"] = True
        apply_preflight["side_effect_policy"] = {**apply_preflight["side_effect_policy"], "browser_started": True}
        spec = SourceMapSelectedExecutorApplicationHandoffSpec.from_context(
            {
                "source_map_selected_executor_application_handoff": True,
                "source_map_selected_executor_apply_preflight": apply_preflight,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapSelectedExecutorApplicationHandoffManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["ready_for_application_review"])
        self.assertIn("selected_consumer_mismatch", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_review_gate_mismatch", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_apply_preflight_execution_claim_detected", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_apply_preflight_browser_start_detected", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_ready_source_map_selected_executor_apply_preflight")


class SourceMapSelectedExecutorResultCheckpointManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_application_handoff() -> dict:
        apply_preflight = SourceMapSelectedExecutorApplicationHandoffManagerTests._ready_apply_preflight()
        spec = SourceMapSelectedExecutorApplicationHandoffSpec.from_context(
            {
                "source_map_selected_executor_application_handoff": True,
                "source_map_selected_executor_apply_preflight": apply_preflight,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
            }
        )
        return SourceMapSelectedExecutorApplicationHandoffManager().review(spec).descriptor

    @staticmethod
    def _debugger_result() -> dict:
        return {
            "schema_version": "reverse-deepagent.source-map-debugger-execution-result.v1",
            "status": "success",
            "breakpoint_status": "success",
            "selected_action_id": "review-debugger-location-use",
            "selected_consumer": "debugger",
            "selected_review_gate": "explicit_debugger_location_review",
            "approval_record_id": "source-map-selected-executor-approval:review-debugger-location-use",
            "reviewer": "analyst",
            "review_approved": True,
            "approve_source_map_debugger_action": True,
            "mode": "apply",
            "breakpoint_count": 1,
            "breakpoint_set": True,
            "browser_started": True,
            "runtime_evaluated": False,
            "cdp_command_sent": True,
            "debugger_location_applied": True,
            "debugger_execution_performed": True,
            "surface_executor_invoked": True,
            "automatic_continuation": False,
            "automatic_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    def test_source_map_selected_executor_result_checkpoint_reviews_successful_application_result_without_execution(self) -> None:
        handoff = self._ready_application_handoff()
        application_result = self._debugger_result()
        result_digest = hashlib.sha256(json.dumps(application_result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        handoff_digest = hashlib.sha256(json.dumps(handoff, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapSelectedExecutorResultCheckpointSpec.from_context(
            {
                "source_map_selected_executor_result_checkpoint": True,
                "source_map_selected_executor_application_handoff": handoff,
                "source_map_selected_executor_application_result": application_result,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
                "expected_application_result_digest_sha256": result_digest,
                "expected_application_handoff_digest_sha256": handoff_digest,
                "reviewer": "analyst",
            }
        )

        result = SourceMapSelectedExecutorResultCheckpointManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["checkpoint_only"])
        self.assertTrue(descriptor["application_result_checkpoint_only"])
        self.assertEqual(descriptor["selected_action_id"], "review-debugger-location-use")
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["application_surface"], "source-map-debugger-application")
        self.assertEqual(descriptor["application_result_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertEqual(descriptor["application_result_status"], "success")
        self.assertEqual(descriptor["application_result_digest_sha256"], result_digest)
        self.assertEqual(descriptor["source_application_handoff_digest_sha256"], handoff_digest)
        self.assertTrue(descriptor["application_handoff_verified"])
        self.assertTrue(descriptor["application_result_verified"])
        self.assertTrue(descriptor["result_success"])
        self.assertEqual(descriptor["result_success_key"], "debugger_location_applied")
        self.assertTrue(descriptor["ready_for_next_explicit_review"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["execute_next_automatically"])
        self.assertFalse(descriptor["automatic_followthrough_supported"])
        self.assertTrue(descriptor["observed_application_side_effects"]["browser_started"])
        self.assertTrue(descriptor["observed_application_side_effects"]["cdp_command_sent"])
        self.assertFalse(descriptor["browser_started_by_checkpoint"])
        self.assertFalse(descriptor["cdp_command_sent_by_checkpoint"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_selected_executor_result_checkpoint")

    def test_source_map_selected_executor_result_checkpoint_blocks_failed_or_automated_application_result(self) -> None:
        handoff = self._ready_application_handoff()
        application_result = self._debugger_result()
        application_result["status"] = "failed"
        application_result["debugger_location_applied"] = False
        application_result["automatic_continuation"] = True
        application_result["calls_mcp"] = True
        spec = SourceMapSelectedExecutorResultCheckpointSpec.from_context(
            {
                "source_map_selected_executor_result_checkpoint": True,
                "source_map_selected_executor_application_handoff": handoff,
                "source_map_selected_executor_application_result": application_result,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapSelectedExecutorResultCheckpointManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["application_result_verified"])
        self.assertIn("source_map_selected_executor_application_result_not_success", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_application_result_success_flag_missing", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_application_result_automatic_continuation_forbidden", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_application_result_calls_mcp_forbidden", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "inspect_source_map_selected_executor_result_checkpoint_failure")


class SourceMapFollowthroughCompletionCheckpointManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_result_checkpoint(consumer: str = "debugger") -> dict:
        surface = {
            "debugger": "source-map-debugger-application",
            "hook": "source-map-hook-application",
            "source-logpoint": "source-map-source-logpoint-application",
            "rebuild": "source-map-rebuild-metadata-application",
        }[consumer]
        artifact = {
            "debugger": "workspace/source-map-debugger-execution-result.json",
            "hook": "workspace/source-map-hook-install-result.json",
            "source-logpoint": "workspace/source-map-source-logpoint-install-result.json",
            "rebuild": "workspace/source-map-rebuild-result.json",
        }[consumer]
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1",
            "status": "ready_for_review",
            "review_only": True,
            "checkpoint_only": True,
            "selected_action_id": f"review-{consumer}-source-map-use",
            "selected_consumer": consumer,
            "selected_review_gate": "explicit_source_map_review",
            "application_surface": surface,
            "application_result_artifact": artifact,
            "application_result_status": "success",
            "application_result_verified": True,
            "application_handoff_verified": True,
            "ready_for_next_explicit_review": True,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "side_effect_policy": {
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    def test_source_map_followthrough_completion_checkpoint_marks_debugger_terminal_review_candidate(self) -> None:
        checkpoint = self._ready_result_checkpoint("debugger")
        digest = hashlib.sha256(json.dumps(checkpoint, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapFollowthroughCompletionCheckpointSpec.from_context(
            {
                "source_map_followthrough_completion_checkpoint": True,
                "source_map_selected_executor_result_checkpoint": checkpoint,
                "expected_consumer": "debugger",
                "expected_result_checkpoint_digest_sha256": digest,
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughCompletionCheckpointManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-completion-checkpoint.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["checkpoint_only"])
        self.assertTrue(descriptor["completion_checkpoint_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["source_result_checkpoint_digest_sha256"], digest)
        self.assertTrue(descriptor["result_checkpoint_verified"])
        self.assertTrue(descriptor["terminal_review_candidate"])
        self.assertFalse(descriptor["followup_required"])
        self.assertEqual(descriptor["completion_status"], "terminal_review_candidate")
        self.assertEqual(descriptor["completion_review"]["recommended_review_action"], "inspect_source_map_debugger_execution_artifacts")
        self.assertIn("workspace/breakpoints.json", descriptor["completion_review"]["required_artifacts"])
        self.assertTrue(descriptor["ready_for_completion_review"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["execute_next_automatically"])
        self.assertFalse(descriptor["browser_started_by_completion"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "inspect_source_map_debugger_execution_artifacts")

    def test_source_map_followthrough_completion_checkpoint_requires_rebuild_generation_followup(self) -> None:
        checkpoint = self._ready_result_checkpoint("rebuild")
        spec = SourceMapFollowthroughCompletionCheckpointSpec.from_context(
            {
                "source_map_followthrough_completion_checkpoint": True,
                "source_map_selected_executor_result_checkpoint": checkpoint,
                "expected_consumer": "rebuild",
            }
        )

        result = SourceMapFollowthroughCompletionCheckpointManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(result.descriptor["selected_consumer"], "rebuild")
        self.assertFalse(result.descriptor["terminal_review_candidate"])
        self.assertTrue(result.descriptor["followup_required"])
        self.assertEqual(result.descriptor["completion_status"], "followup_required")
        self.assertEqual(result.descriptor["next_action"], "review_source_map_rebuild_generation")
        self.assertIn("source_map_rebuild_generation_not_attached_to_completion_checkpoint", result.descriptor["warnings"])

    def test_source_map_followthrough_completion_checkpoint_blocks_bad_checkpoint_or_forbidden_automation(self) -> None:
        checkpoint = self._ready_result_checkpoint("debugger")
        checkpoint["status"] = "blocked"
        checkpoint["execute_next_automatically"] = True
        spec = SourceMapFollowthroughCompletionCheckpointSpec.from_context(
            {
                "source_map_followthrough_completion_checkpoint": True,
                "source_map_selected_executor_result_checkpoint": checkpoint,
            }
        )

        result = SourceMapFollowthroughCompletionCheckpointManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["ready_for_completion_review"])
        self.assertIn("source_map_selected_executor_result_checkpoint_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_result_checkpoint_execute_next_automatically_forbidden", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "inspect_source_map_followthrough_completion_checkpoint_failure")


class SourceMapTerminalReviewPackageManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_completion_checkpoint(consumer: str = "debugger") -> dict:
        result_checkpoint = SourceMapFollowthroughCompletionCheckpointManagerTests._ready_result_checkpoint(consumer)
        return SourceMapFollowthroughCompletionCheckpointManager().review(
            SourceMapFollowthroughCompletionCheckpointSpec.from_context(
                {
                    "source_map_followthrough_completion_checkpoint": True,
                    "source_map_selected_executor_result_checkpoint": result_checkpoint,
                    "expected_consumer": consumer,
                }
            )
        ).descriptor

    def test_source_map_terminal_review_package_packages_ready_completion_without_execution(self) -> None:
        completion = self._ready_completion_checkpoint("debugger")
        digest = hashlib.sha256(json.dumps(completion, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapTerminalReviewPackageSpec.from_context(
            {
                "source_map_terminal_review_package": True,
                "source_map_followthrough_completion_checkpoint": completion,
                "expected_consumer": "debugger",
                "expected_completion_checkpoint_digest_sha256": digest,
                "reviewer": "analyst",
            }
        )

        result = SourceMapTerminalReviewPackageManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-terminal-review-package.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["audit_handoff_only"])
        self.assertTrue(descriptor["terminal_review_package_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["source_completion_checkpoint_digest_sha256"], digest)
        self.assertTrue(descriptor["completion_checkpoint_verified"])
        self.assertTrue(descriptor["terminal_review_candidate"])
        self.assertFalse(descriptor["followup_required"])
        self.assertTrue(descriptor["ready_for_terminal_review"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["execute_next_automatically"])
        self.assertFalse(descriptor["recommended_action_executed"])
        package = descriptor["terminal_review_package"]
        self.assertEqual(package["schema_version"], "reverse-deepagent.source-map-terminal-review-package.payload.v1")
        self.assertEqual(package["package_kind"], "terminal-review-package")
        self.assertEqual(package["recommended_review_action"], "inspect_source_map_debugger_execution_artifacts")
        self.assertIn("workspace/breakpoints.json", package["required_artifacts"])
        self.assertFalse(package["execute_recommended_action"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_terminal_review_package")

    def test_source_map_terminal_review_package_blocks_bad_completion_checkpoint(self) -> None:
        completion = self._ready_completion_checkpoint("debugger")
        completion["status"] = "blocked"
        completion["ready_to_execute_now"] = True
        spec = SourceMapTerminalReviewPackageSpec.from_context(
            {
                "source_map_terminal_review_package": True,
                "source_map_followthrough_completion_checkpoint": completion,
            }
        )

        result = SourceMapTerminalReviewPackageManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["ready_for_terminal_review"])
        self.assertIn("source_map_followthrough_completion_checkpoint_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_completion_checkpoint_ready_to_execute_now_forbidden", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "inspect_source_map_terminal_review_package_failure")


class SourceMapTerminalReviewClosureCheckpointManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_terminal_review_package(consumer: str = "debugger") -> dict:
        completion = SourceMapTerminalReviewPackageManagerTests._ready_completion_checkpoint(consumer)
        return SourceMapTerminalReviewPackageManager().review(
            SourceMapTerminalReviewPackageSpec.from_context(
                {
                    "source_map_terminal_review_package": True,
                    "source_map_followthrough_completion_checkpoint": completion,
                    "expected_consumer": consumer,
                    "reviewer": "analyst",
                }
            )
        ).descriptor

    def test_source_map_terminal_review_closure_checkpoint_records_observed_review_without_execution(self) -> None:
        package = self._ready_terminal_review_package("debugger")
        digest = hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        observed = {
            "schema_version": "reverse-deepagent.source-map-terminal-review-observed-result.v1",
            "status": "reviewed",
            "review_completed": True,
            "observed_review_action": "inspect_source_map_debugger_execution_artifacts",
            "reviewer": "analyst",
            "review_notes": "breakpoint artifacts reviewed",
        }
        spec = SourceMapTerminalReviewClosureCheckpointSpec.from_context(
            {
                "source_map_terminal_review_closure_checkpoint": True,
                "source_map_terminal_review_package": package,
                "source_map_terminal_review_observed_result": observed,
                "expected_consumer": "debugger",
                "expected_terminal_review_package_digest_sha256": digest,
                "reviewer": "analyst",
            }
        )

        result = SourceMapTerminalReviewClosureCheckpointManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["audit_checkpoint_only"])
        self.assertTrue(descriptor["closure_checkpoint_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["source_terminal_review_package_digest_sha256"], digest)
        self.assertTrue(descriptor["terminal_review_package_verified"])
        self.assertTrue(descriptor["observed_result_attached"])
        self.assertTrue(descriptor["observed_review_completed"])
        self.assertEqual(descriptor["closure_status"], "terminal_review_observed")
        self.assertTrue(descriptor["ready_for_closure_audit_review"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["execute_next_automatically"])
        self.assertFalse(descriptor["recommended_action_executed_by_checkpoint"])
        audit = descriptor["closure_audit"]
        self.assertEqual(audit["schema_version"], "reverse-deepagent.source-map-terminal-review-closure-audit.v1")
        self.assertEqual(audit["observed_review_action"], "inspect_source_map_debugger_execution_artifacts")
        self.assertTrue(audit["manual_review_observed"])
        self.assertFalse(audit["execute_recommended_action"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_terminal_review_closure_checkpoint")

    def test_source_map_terminal_review_closure_checkpoint_blocks_missing_observed_result_and_forbidden_package_automation(self) -> None:
        package = self._ready_terminal_review_package("debugger")
        package["ready_to_execute_now"] = True
        spec = SourceMapTerminalReviewClosureCheckpointSpec.from_context(
            {
                "source_map_terminal_review_closure_checkpoint": True,
                "source_map_terminal_review_package": package,
            }
        )

        result = SourceMapTerminalReviewClosureCheckpointManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["ready_for_closure_audit_review"])
        self.assertIn("source_map_terminal_review_observed_result_missing", result.descriptor["blockers"])
        self.assertIn("source_map_terminal_review_package_ready_to_execute_now_forbidden", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "record_source_map_terminal_review_observed_result")


class SourceMapTerminalReviewFinalAuditManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_closure_checkpoint(consumer: str = "debugger") -> dict:
        package = SourceMapTerminalReviewClosureCheckpointManagerTests._ready_terminal_review_package(consumer)
        observed = {
            "schema_version": "reverse-deepagent.source-map-terminal-review-observed-result.v1",
            "status": "reviewed",
            "review_completed": True,
            "observed_review_action": "inspect_source_map_debugger_execution_artifacts" if consumer == "debugger" else "inspect_source_map_terminal_review_artifacts",
            "reviewer": "analyst",
        }
        return SourceMapTerminalReviewClosureCheckpointManager().review(
            SourceMapTerminalReviewClosureCheckpointSpec.from_context(
                {
                    "source_map_terminal_review_closure_checkpoint": True,
                    "source_map_terminal_review_package": package,
                    "source_map_terminal_review_observed_result": observed,
                    "expected_consumer": consumer,
                    "reviewer": "analyst",
                }
            )
        ).descriptor

    def test_source_map_terminal_review_final_audit_rolls_up_ready_closure_without_execution(self) -> None:
        closure = self._ready_closure_checkpoint("debugger")
        digest = hashlib.sha256(json.dumps(closure, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapTerminalReviewFinalAuditSpec.from_context(
            {
                "source_map_terminal_review_final_audit": True,
                "source_map_terminal_review_closure_checkpoint": closure,
                "expected_consumer": "debugger",
                "expected_closure_checkpoint_digest_sha256": digest,
                "reviewer": "analyst",
            }
        )

        result = SourceMapTerminalReviewFinalAuditManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-terminal-review-final-audit.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["audit_rollup_only"])
        self.assertTrue(descriptor["final_audit_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["source_closure_checkpoint_digest_sha256"], digest)
        self.assertTrue(descriptor["closure_checkpoint_verified"])
        self.assertEqual(descriptor["final_audit_status"], "source_map_followthrough_review_closed")
        self.assertTrue(descriptor["ready_for_final_audit_review"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["execute_next_automatically"])
        self.assertFalse(descriptor["recommended_action_executed_by_rollup"])
        rollup = descriptor["final_audit_rollup"]
        self.assertEqual(rollup["schema_version"], "reverse-deepagent.source-map-terminal-review-final-audit-rollup.v1")
        self.assertEqual(rollup["observed_review_action"], "inspect_source_map_debugger_execution_artifacts")
        self.assertTrue(rollup["manual_review_observed"])
        self.assertFalse(rollup["execute_recommended_action"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_terminal_review_final_audit")

    def test_source_map_terminal_review_final_audit_blocks_bad_closure_checkpoint(self) -> None:
        closure = self._ready_closure_checkpoint("debugger")
        closure["status"] = "blocked"
        closure["ready_to_execute_now"] = True
        spec = SourceMapTerminalReviewFinalAuditSpec.from_context(
            {
                "source_map_terminal_review_final_audit": True,
                "source_map_terminal_review_closure_checkpoint": closure,
            }
        )

        result = SourceMapTerminalReviewFinalAuditManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["ready_for_final_audit_review"])
        self.assertIn("source_map_terminal_review_closure_checkpoint_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_terminal_review_closure_checkpoint_ready_to_execute_now_forbidden", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "inspect_source_map_terminal_review_final_audit_failure")


class SourceMapTerminalReviewActionDecisionManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_terminal_review_package(consumer: str = "debugger") -> dict:
        return SourceMapTerminalReviewClosureCheckpointManagerTests._ready_terminal_review_package(consumer)

    @staticmethod
    def _ready_closure_checkpoint(consumer: str = "debugger") -> dict:
        return SourceMapTerminalReviewFinalAuditManagerTests._ready_closure_checkpoint(consumer)

    @staticmethod
    def _ready_final_audit(consumer: str = "debugger") -> dict:
        closure = SourceMapTerminalReviewActionDecisionManagerTests._ready_closure_checkpoint(consumer)
        return SourceMapTerminalReviewFinalAuditManager().review(
            SourceMapTerminalReviewFinalAuditSpec.from_context(
                {
                    "source_map_terminal_review_final_audit": True,
                    "source_map_terminal_review_closure_checkpoint": closure,
                    "expected_consumer": consumer,
                    "reviewer": "analyst",
                }
            )
        ).descriptor

    def test_source_map_terminal_review_action_decision_records_ready_package_without_execution(self) -> None:
        package = self._ready_terminal_review_package("debugger")
        digest = hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapTerminalReviewActionDecisionSpec.from_context(
            {
                "record_source_map_terminal_review_action": True,
                "source_map_terminal_review_package": package,
                "selected_action": "request_manual_execution",
                "reviewer": "analyst",
                "reason": "reviewed debugger artifacts; execute manually in a separate step",
                "expected_source_descriptor_digest_sha256": digest,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapTerminalReviewActionDecisionManager().record(spec)

        self.assertEqual(result.status, "recorded")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-terminal-review-action-decision.v1")
        self.assertTrue(descriptor["explicit_review_only"])
        self.assertTrue(descriptor["decision_record_only"])
        self.assertEqual(descriptor["source_descriptor_kind"], "source-map-terminal-review-package")
        self.assertEqual(descriptor["source_descriptor_digest_sha256"], digest)
        self.assertEqual(descriptor["selected_action"], "request_manual_execution")
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["recommended_review_action"], "inspect_source_map_debugger_execution_artifacts")
        self.assertTrue(descriptor["terminal_review_action_recorded"])
        self.assertTrue(descriptor["recommended_action_approved_for_separate_followup"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["execute_next_automatically"])
        self.assertFalse(descriptor["executes_recommended_action"])
        self.assertFalse(descriptor["installs_hook"])
        self.assertFalse(descriptor["installs_logpoint"])
        self.assertFalse(descriptor["continues_debugger"])
        self.assertFalse(descriptor["generates_rebuild"])
        self.assertFalse(descriptor["fetches_source_map"])
        self.assertFalse(descriptor["exports_raw_source"])
        self.assertFalse(result.side_effect_policy["executes_recommended_action"])
        self.assertFalse(result.side_effect_policy["installs_hook"])
        self.assertFalse(result.side_effect_policy["installs_logpoint"])
        self.assertFalse(result.side_effect_policy["continues_debugger"])
        self.assertFalse(result.side_effect_policy["generates_rebuild"])
        self.assertFalse(result.side_effect_policy["fetches_source_map"])
        self.assertFalse(result.side_effect_policy["exports_raw_source"])
        self.assertEqual(descriptor["decision_record"]["schema_version"], "reverse-deepagent.source-map-terminal-review-action-result.v1")
        self.assertEqual(descriptor["next_action"], "perform_separate_explicit_manual_followup_if_approved")

    def test_source_map_terminal_review_action_decision_consumes_final_audit(self) -> None:
        final_audit = self._ready_final_audit("debugger")
        spec = SourceMapTerminalReviewActionDecisionSpec.from_context(
            {
                "source_map_terminal_review_action_decision": True,
                "source_map_terminal_review_final_audit": final_audit,
                "selected_action": "mark_complete",
                "reviewer": "analyst",
                "reason": "final audit reviewed and no follow-up remains",
            }
        )

        result = SourceMapTerminalReviewActionDecisionManager().record(spec)

        self.assertEqual(result.status, "recorded")
        self.assertEqual(result.descriptor["source_descriptor_kind"], "source-map-terminal-review-final-audit")
        self.assertTrue(result.descriptor["terminal_review_marked_complete"])
        self.assertFalse(result.descriptor["executes_recommended_action"])
        self.assertFalse(result.descriptor["continues_debugger"])

    def test_source_map_terminal_review_action_decision_blocks_without_ready_terminal_source(self) -> None:
        spec = SourceMapTerminalReviewActionDecisionSpec.from_context(
            {
                "source_map_terminal_review_action_decision": True,
                "selected_action": "defer",
                "reviewer": "analyst",
                "reason": "waiting for package",
            }
        )

        result = SourceMapTerminalReviewActionDecisionManager().record(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["terminal_review_action_recorded"])
        self.assertIn("source_map_terminal_review_ready_source_missing", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_ready_source_map_terminal_review_artifact")

    def test_source_map_terminal_review_action_decision_blocks_invalid_action(self) -> None:
        package = self._ready_terminal_review_package("debugger")
        spec = SourceMapTerminalReviewActionDecisionSpec.from_context(
            {
                "source_map_terminal_review_action_decision": True,
                "source_map_terminal_review_package": package,
                "selected_action": "execute_debugger_now",
                "reviewer": "analyst",
                "reason": "bad action should be blocked",
            }
        )

        result = SourceMapTerminalReviewActionDecisionManager().record(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_terminal_review_action_invalid", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["terminal_review_action_recorded"])
        self.assertFalse(result.descriptor["executes_recommended_action"])
        self.assertEqual(result.descriptor["next_action"], "choose_valid_source_map_terminal_review_action")

    def test_source_map_terminal_review_action_decision_excludes_raw_source(self) -> None:
        package = self._ready_terminal_review_package("debugger")
        package["raw_source"] = "function secret() { return 1 }"
        package["sourcesContent"] = ["const token = 'secret';"]
        spec = SourceMapTerminalReviewActionDecisionSpec.from_context(
            {
                "source_map_terminal_review_action_result": True,
                "source_map_terminal_review_package": package,
                "selected_action": "defer",
                "reviewer": "analyst",
                "reason": "defer pending manual review",
            }
        )

        result = SourceMapTerminalReviewActionDecisionManager().record(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_terminal_review_source_raw_source_material_forbidden", result.descriptor["blockers"])
        self.assertFalse(result.descriptor["terminal_review_action_recorded"])
        rendered = json.dumps(result.descriptor, sort_keys=True, ensure_ascii=False)
        self.assertNotIn("function secret", rendered)
        self.assertNotIn("sourcesContent", rendered)
        self.assertNotIn("const token", rendered)
        self.assertFalse(result.descriptor["exports_raw_source"])
        self.assertFalse(result.side_effect_policy["exports_raw_source"])

    def test_source_map_terminal_review_action_decision_digest_and_idempotency_are_deterministic(self) -> None:
        closure = self._ready_closure_checkpoint("debugger")
        context = {
            "record_source_map_terminal_review_action": True,
            "source_map_terminal_review_closure_checkpoint": closure,
            "selected_action": "approve-followup",
            "reviewer": "analyst",
            "reason": "same reviewed decision",
        }

        first = SourceMapTerminalReviewActionDecisionManager().record(SourceMapTerminalReviewActionDecisionSpec.from_context(dict(context))).descriptor
        second = SourceMapTerminalReviewActionDecisionManager().record(SourceMapTerminalReviewActionDecisionSpec.from_context(dict(context))).descriptor

        self.assertEqual(first["status"], "recorded")
        self.assertEqual(first["source_descriptor_kind"], "source-map-terminal-review-closure-checkpoint")
        self.assertEqual(first["selected_action"], "approve_followup")
        self.assertEqual(first["decision_id"], second["decision_id"])
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertEqual(first["decision_digest_sha256"], second["decision_digest_sha256"])



class SourceMapFollowthroughChainReadinessManagerTests(unittest.TestCase):
    def test_source_map_followthrough_chain_readiness_reports_furthest_ready_stage_without_execution(self) -> None:
        approval_plan = SourceMapSelectedExecutorApplyPreflightManagerTests._ready_approval_plan()
        approval_record = SourceMapSelectedExecutorApplyPreflightManagerTests._approval_record(approval_plan)
        apply_preflight = SourceMapSelectedExecutorApplyPreflightManager().review(
            SourceMapSelectedExecutorApplyPreflightSpec.from_context(
                {
                    "source_map_selected_executor_apply_preflight": True,
                    "source_map_selected_executor_approval_plan": approval_plan,
                    "source_map_selected_executor_approval_record": approval_record,
                    "expected_consumer": "debugger",
                }
            )
        ).descriptor
        spec = SourceMapFollowthroughChainReadinessSpec.from_context(
            {
                "source_map_followthrough_chain_readiness": True,
                "source_map_selected_executor_approval_plan": approval_plan,
                "source_map_selected_executor_approval_record": approval_record,
                "source_map_selected_executor_apply_preflight": apply_preflight,
                "expected_consumer": "debugger",
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughChainReadinessManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-chain-readiness.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["readiness_descriptor_only"])
        self.assertTrue(descriptor["orchestration_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["completed_stage"], "source_map_selected_executor_apply_preflight")
        self.assertEqual(descriptor["next_stage"], "selected_executor_result_review")
        self.assertEqual(descriptor["next_required_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertEqual(descriptor["next_action"], "review_source_map_debugger_executor_application")
        self.assertTrue(descriptor["ready_for_selected_executor_review"])
        self.assertFalse(descriptor["selected_executor_result_ready"])
        self.assertFalse(descriptor["automatic_followthrough_supported"])
        self.assertFalse(descriptor["automatic_debugger_continuation_supported"])
        self.assertFalse(descriptor["automatic_hook_install_supported"])
        self.assertFalse(descriptor["automatic_source_logpoint_install_supported"])
        self.assertFalse(descriptor["automatic_raw_source_rebuild_supported"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["hook_installed"])
        self.assertFalse(result.side_effect_policy["rebuild_executed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertIn("workspace/source-map-readiness.json", descriptor["missing_required_artifacts"])
        self.assertEqual(descriptor["blockers"], [])

    def test_source_map_followthrough_chain_readiness_blocks_failed_stage_evidence(self) -> None:
        spec = SourceMapFollowthroughChainReadinessSpec.from_context(
            {
                "source_map_followthrough_chain_readiness": True,
                "source_map_selected_executor_input_review": {
                    "schema_version": "reverse-deepagent.source-map-selected-executor-input-review.v1",
                    "status": "blocked",
                    "ready_for_executor_review": False,
                    "blockers": ["selected_executor_input_missing"],
                    "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False},
                },
            }
        )

        result = SourceMapFollowthroughChainReadinessManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("source_map_selected_executor_input_review_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_selected_executor_input_review:selected_executor_input_missing", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "resolve_source_map_followthrough_chain_readiness_blockers")
        self.assertFalse(result.side_effect_policy["browser_started"])



class SourceMapFollowthroughOneStepPlanManagerTests(unittest.TestCase):
    def test_source_map_followthrough_one_step_plan_packages_next_review_without_execution(self) -> None:
        chain = {
            "schema_version": "reverse-deepagent.source-map-followthrough-chain-readiness.v1",
            "status": "ready_for_review",
            "selected_consumer": "debugger",
            "completed_stage": "source_map_selected_executor_apply_preflight",
            "next_stage": "selected_executor_result_review",
            "next_required_artifact": "workspace/source-map-debugger-execution-result.json",
            "next_action": "review_source_map_debugger_executor_application",
            "selected_executor_result_ready": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": [],
            "missing_required_artifacts": ["workspace/source-map-readiness.json"],
            "side_effect_policy": {
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        spec = SourceMapFollowthroughOneStepPlanSpec.from_context(
            {
                "source_map_followthrough_one_step_plan": True,
                "source_map_followthrough_chain_readiness": chain,
                "expected_consumer": "debugger",
                "expected_next_action": "review_source_map_debugger_executor_application",
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughOneStepPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-one-step-plan.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["plan_only"])
        self.assertTrue(descriptor["one_step_plan_only"])
        self.assertTrue(descriptor["orchestration_only"])
        self.assertTrue(descriptor["handoff_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["source_chain_completed_stage"], "source_map_selected_executor_apply_preflight")
        self.assertEqual(descriptor["source_chain_next_stage"], "selected_executor_result_review")
        self.assertEqual(descriptor["source_chain_next_required_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertEqual(descriptor["source_chain_next_action"], "review_source_map_debugger_executor_application")
        self.assertTrue(descriptor["planned_step_ready_for_review"])
        self.assertEqual(descriptor["next_action"], "review_source_map_followthrough_one_step_plan_before_next_action")
        planned_step = descriptor["planned_step"]
        self.assertEqual(planned_step["step_schema_version"], "reverse-deepagent.source-map-followthrough-one-step.v1")
        self.assertEqual(planned_step["selected_consumer"], "debugger")
        self.assertEqual(planned_step["next_action"], "review_source_map_debugger_executor_application")
        self.assertEqual(planned_step["next_required_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertTrue(planned_step["requires_explicit_review"])
        self.assertTrue(planned_step["requires_separate_executor_call"])
        self.assertFalse(planned_step["execute_automatically"])
        self.assertFalse(planned_step["executor_invoked"])
        self.assertFalse(planned_step["approval_recorded"])
        self.assertFalse(planned_step["apply_preflight_invoked"])
        self.assertFalse(descriptor["will_invoke_next_action"])
        self.assertFalse(descriptor["will_record_approval"])
        self.assertFalse(descriptor["will_run_apply_preflight"])
        self.assertFalse(descriptor["will_execute_debugger"])
        self.assertFalse(descriptor["will_install_hook"])
        self.assertFalse(descriptor["will_run_rebuild"])
        self.assertFalse(descriptor["automatic_followthrough_supported"])
        self.assertFalse(descriptor["automatic_execution_supported"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["hook_installed"])
        self.assertFalse(result.side_effect_policy["rebuild_executed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertIn("source_map_followthrough_one_step_plan_is_not_an_executor", descriptor["warnings"])

    def test_source_map_followthrough_one_step_plan_blocks_failed_or_mismatched_chain(self) -> None:
        chain = {
            "schema_version": "reverse-deepagent.source-map-followthrough-chain-readiness.v1",
            "status": "blocked",
            "selected_consumer": "hook",
            "next_required_artifact": "workspace/source-map-hook-install-result.json",
            "next_action": "review_source_map_hook_executor_application",
            "blockers": ["source_map_selected_executor_input_review_not_ready"],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False},
        }
        spec = SourceMapFollowthroughOneStepPlanSpec.from_context(
            {
                "source_map_followthrough_one_step_plan": True,
                "source_map_followthrough_chain_readiness": chain,
                "expected_consumer": "debugger",
                "expected_next_action": "review_source_map_debugger_executor_application",
            }
        )

        result = SourceMapFollowthroughOneStepPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["planned_step_ready_for_review"])
        self.assertIn("source_map_followthrough_chain_readiness_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_chain_readiness:source_map_selected_executor_input_review_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_one_step_consumer_mismatch", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_one_step_next_action_mismatch", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_ready_source_map_followthrough_chain_readiness_descriptor")


class SourceMapFollowthroughDispatchPreflightManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_one_step_plan() -> dict:
        chain = {
            "schema_version": "reverse-deepagent.source-map-followthrough-chain-readiness.v1",
            "status": "ready_for_review",
            "selected_consumer": "debugger",
            "completed_stage": "source_map_selected_executor_apply_preflight",
            "next_stage": "selected_executor_result_review",
            "next_required_artifact": "workspace/source-map-debugger-execution-result.json",
            "next_action": "review_source_map_debugger_executor_application",
            "selected_executor_result_ready": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": [],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        return SourceMapFollowthroughOneStepPlanManager().review(
            SourceMapFollowthroughOneStepPlanSpec.from_context(
                {
                    "source_map_followthrough_one_step_plan": True,
                    "source_map_followthrough_chain_readiness": chain,
                    "expected_consumer": "debugger",
                }
            )
        ).descriptor

    def test_source_map_followthrough_dispatch_preflight_reviews_known_dispatch_target_without_execution(self) -> None:
        one_step_plan = self._ready_one_step_plan()
        spec = SourceMapFollowthroughDispatchPreflightSpec.from_context(
            {
                "source_map_followthrough_dispatch_preflight": True,
                "source_map_followthrough_one_step_plan": one_step_plan,
                "expected_consumer": "debugger",
                "expected_next_action": "review_source_map_debugger_executor_application",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughDispatchPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-preflight.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["preflight_only"])
        self.assertTrue(descriptor["dispatch_preflight_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["planned_next_action"], "review_source_map_debugger_executor_application")
        self.assertEqual(descriptor["planned_required_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertEqual(descriptor["dispatch_target"]["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(descriptor["dispatcher_input_ready_for_review"])
        dispatcher_input = descriptor["dispatcher_input"]
        self.assertEqual(dispatcher_input["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-input.v1")
        self.assertEqual(dispatcher_input["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(dispatcher_input["requires_explicit_review"])
        self.assertTrue(dispatcher_input["requires_separate_executor_call"])
        self.assertFalse(dispatcher_input["dispatcher_invoked"])
        self.assertFalse(dispatcher_input["executor_invoked"])
        self.assertFalse(descriptor["will_invoke_dispatch_target"])
        self.assertFalse(descriptor["will_invoke_next_action"])
        self.assertFalse(descriptor["will_execute_debugger"])
        self.assertFalse(descriptor["will_install_hook"])
        self.assertFalse(descriptor["will_run_rebuild"])
        self.assertFalse(descriptor["automatic_dispatch_supported"])
        self.assertFalse(descriptor["automatic_followthrough_supported"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_followthrough_dispatch_preflight_before_explicit_executor_call")

    def test_source_map_followthrough_dispatch_preflight_blocks_unready_or_mismatched_plan(self) -> None:
        spec = SourceMapFollowthroughDispatchPreflightSpec.from_context(
            {
                "source_map_followthrough_dispatch_preflight": True,
                "source_map_followthrough_one_step_plan": {
                    "schema_version": "reverse-deepagent.source-map-followthrough-one-step-plan.v1",
                    "status": "blocked",
                    "selected_consumer": "hook",
                    "planned_step_ready_for_review": False,
                    "planned_step": {},
                    "blockers": ["source_map_followthrough_one_step_consumer_mismatch"],
                    "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False},
                },
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapFollowthroughDispatchPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["dispatcher_input_ready_for_review"])
        self.assertIn("source_map_followthrough_one_step_plan_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_one_step_plan:source_map_followthrough_one_step_consumer_mismatch", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_one_step_planned_step_missing", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_ready_source_map_followthrough_one_step_plan_descriptor")


class SourceMapFollowthroughDispatchApprovalPlanManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_dispatch_preflight() -> dict:
        one_step_plan = SourceMapFollowthroughDispatchPreflightManagerTests._ready_one_step_plan()
        return SourceMapFollowthroughDispatchPreflightManager().review(
            SourceMapFollowthroughDispatchPreflightSpec.from_context(
                {
                    "source_map_followthrough_dispatch_preflight": True,
                    "source_map_followthrough_one_step_plan": one_step_plan,
                    "expected_consumer": "debugger",
                }
            )
        ).descriptor

    def test_source_map_followthrough_dispatch_approval_plan_reviews_gates_without_recording_approval(self) -> None:
        preflight = self._ready_dispatch_preflight()
        spec = SourceMapFollowthroughDispatchApprovalPlanSpec.from_context(
            {
                "source_map_followthrough_dispatch_approval_plan": True,
                "source_map_followthrough_dispatch_preflight": preflight,
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughDispatchApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-approval-plan.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["approval_plan_only"])
        self.assertTrue(descriptor["transaction_plan_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertEqual(descriptor["planned_required_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertTrue(descriptor["approval_plan_ready_for_review"])
        self.assertTrue(descriptor["transaction_plan_ready_for_review"])
        approval_plan = descriptor["approval_plan"]
        transaction_plan = descriptor["transaction_plan"]
        self.assertEqual(approval_plan["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-approval.v1")
        self.assertTrue(approval_plan["requires_explicit_review"])
        self.assertTrue(approval_plan["requires_approval_record"])
        self.assertTrue(approval_plan["requires_transaction_journal"])
        self.assertFalse(approval_plan["approval_recorded"])
        self.assertFalse(approval_plan["ready_to_dispatch_now"])
        self.assertEqual(transaction_plan["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-transaction-plan.v1")
        self.assertFalse(transaction_plan["transaction_started"])
        self.assertFalse(transaction_plan["journal_written_now"])
        self.assertTrue(transaction_plan["journal_required_before_dispatch"])
        self.assertFalse(descriptor["ready_to_dispatch_now"])
        self.assertFalse(descriptor["approval_recorded"])
        self.assertFalse(descriptor["transaction_started"])
        self.assertFalse(descriptor["journal_written"])
        self.assertFalse(descriptor["will_write_approval_record"])
        self.assertFalse(descriptor["will_start_transaction"])
        self.assertFalse(descriptor["will_invoke_dispatch_target"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_followthrough_dispatch_approval_plan_before_recording_approval")

    def test_source_map_followthrough_dispatch_approval_plan_blocks_unready_preflight(self) -> None:
        spec = SourceMapFollowthroughDispatchApprovalPlanSpec.from_context(
            {
                "source_map_followthrough_dispatch_approval_plan": True,
                "source_map_followthrough_dispatch_preflight": {
                    "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-preflight.v1",
                    "status": "blocked",
                    "selected_consumer": "debugger",
                    "dispatcher_input_ready_for_review": False,
                    "dispatcher_input": {},
                    "blockers": ["source_map_followthrough_dispatch_target_unsupported"],
                    "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False},
                },
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapFollowthroughDispatchApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["approval_plan_ready_for_review"])
        self.assertFalse(result.descriptor["transaction_plan_ready_for_review"])
        self.assertIn("source_map_followthrough_dispatch_preflight_not_ready", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_dispatch_preflight:source_map_followthrough_dispatch_target_unsupported", result.descriptor["blockers"])
        self.assertIn("source_map_followthrough_dispatch_preflight_input_not_ready", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_ready_source_map_followthrough_dispatch_preflight_descriptor")


class SourceMapFollowthroughDispatchTransactionPreflightManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_dispatch_approval_plan() -> dict:
        preflight = SourceMapFollowthroughDispatchApprovalPlanManagerTests._ready_dispatch_preflight()
        return SourceMapFollowthroughDispatchApprovalPlanManager().review(
            SourceMapFollowthroughDispatchApprovalPlanSpec.from_context(
                {
                    "source_map_followthrough_dispatch_approval_plan": True,
                    "source_map_followthrough_dispatch_preflight": preflight,
                    "expected_consumer": "debugger",
                    "expected_dispatch_surface": "source-map-debugger-execution-result",
                    "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                    "reviewer": "analyst",
                }
            )
        ).descriptor

    @staticmethod
    def _approval_record_for(approval_descriptor: dict, *, decision: str = "approved", digest: str | None = None) -> dict:
        plan_digest = digest or hashlib.sha256(json.dumps(approval_descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        approval_plan = approval_descriptor["approval_plan"]
        transaction_plan = approval_descriptor["transaction_plan"]
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-approval-record.v1",
            "status": "written",
            "approval_recorded": True,
            "approved_for_dispatch": decision == "approved",
            "decision": decision,
            "approval_record_id": "source-map-followthrough-dispatch-approval-record:test",
            "approval_plan_id": approval_plan["approval_plan_id"],
            "transaction_plan_id": transaction_plan["transaction_plan_id"],
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "approval_plan_digest_sha256": plan_digest,
            "dispatch_input_gates": {
                "approval_recorded": True,
                "approved_for_dispatch": decision == "approved",
                "ready_to_dispatch_now": False,
                "transaction_started": False,
                "journal_written": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "requires_transaction_preflight_followup": True,
                "requires_transaction_journal_before_dispatch": True,
            },
            "side_effect_policy": {
                "approval_record_writer": True,
                "dry_run_is_read_only": True,
                "files_mutated": True,
                "artifacts_written": True,
                "writes_approval_record": True,
                "approval_recorded": True,
                "ready_to_dispatch_now": False,
                "transaction_started": False,
                "journal_written": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    def test_source_map_followthrough_dispatch_transaction_preflight_reviews_approved_record_without_writing_journal(self) -> None:
        approval_descriptor = self._ready_dispatch_approval_plan()
        approval_record = self._approval_record_for(approval_descriptor)
        spec = SourceMapFollowthroughDispatchTransactionPreflightSpec.from_context(
            {
                "source_map_followthrough_dispatch_transaction_preflight": True,
                "source_map_followthrough_dispatch_approval_plan": approval_descriptor,
                "source_map_followthrough_dispatch_approval_record": approval_record,
                "expected_approval_plan_id": approval_descriptor["approval_plan"]["approval_plan_id"],
                "expected_approval_record_id": approval_record["approval_record_id"],
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "expected_plan_digest_sha256": approval_record["approval_plan_digest_sha256"],
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughDispatchTransactionPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["read_only"])
        self.assertTrue(descriptor["transaction_preflight_only"])
        self.assertTrue(descriptor["journal_writer_gate_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertEqual(descriptor["planned_required_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertTrue(descriptor["approval_record_verified"])
        self.assertTrue(descriptor["transaction_plan_verified"])
        self.assertTrue(descriptor["transaction_preflight_ready_for_review"])
        self.assertTrue(descriptor["journal_writer_gate_ready_for_review"])
        self.assertFalse(descriptor["ready_to_write_now"])
        self.assertFalse(descriptor["ready_to_dispatch_now"])
        self.assertFalse(descriptor["transaction_started"])
        self.assertFalse(descriptor["journal_written"])
        self.assertFalse(descriptor["will_write_transaction_journal"])
        self.assertFalse(descriptor["will_invoke_dispatch_target"])
        self.assertFalse(descriptor["will_execute_debugger"])
        self.assertFalse(descriptor["will_install_source_logpoint"])
        self.assertFalse(descriptor["will_install_hook"])
        self.assertFalse(descriptor["will_run_rebuild"])
        self.assertEqual(descriptor["transaction_preflight"]["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight-gate.v1")
        self.assertTrue(descriptor["transaction_preflight"]["approval_record_verified"])
        self.assertFalse(descriptor["transaction_preflight"]["journal_written"])
        self.assertEqual(descriptor["journal_writer_gate"]["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-journal-writer-gate.v1")
        self.assertEqual(descriptor["journal_writer_gate"]["journal_artifact"], "workspace/source-map-followthrough-dispatch-transaction-journal.json")
        self.assertFalse(descriptor["journal_writer_gate"]["journal_written_now"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_followthrough_dispatch_transaction_journal_writer")

    def test_source_map_followthrough_dispatch_transaction_preflight_blocks_mismatched_or_unapproved_record(self) -> None:
        approval_descriptor = self._ready_dispatch_approval_plan()
        approval_record = self._approval_record_for(approval_descriptor, decision="rejected", digest="bad-digest")
        spec = SourceMapFollowthroughDispatchTransactionPreflightSpec.from_context(
            {
                "source_map_followthrough_dispatch_transaction_preflight": True,
                "source_map_followthrough_dispatch_approval_plan": approval_descriptor,
                "source_map_followthrough_dispatch_approval_record": approval_record,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapFollowthroughDispatchTransactionPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        descriptor = result.descriptor
        self.assertFalse(descriptor["approval_record_verified"])
        self.assertFalse(descriptor["transaction_preflight_ready_for_review"])
        self.assertFalse(descriptor["journal_writer_gate_ready_for_review"])
        self.assertIn("source_map_followthrough_dispatch_not_approved", descriptor["blockers"])
        self.assertIn("source_map_followthrough_dispatch_approval_plan_digest_mismatch", descriptor["blockers"])
        self.assertEqual(descriptor["next_action"], "provide_ready_source_map_followthrough_dispatch_approval_plan_descriptor")



class SourceMapFollowthroughDispatchBoundedExecutorGateManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_transaction_journal() -> dict:
        approval_descriptor = SourceMapFollowthroughDispatchTransactionPreflightManagerTests._ready_dispatch_approval_plan()
        approval_record = SourceMapFollowthroughDispatchTransactionPreflightManagerTests._approval_record_for(approval_descriptor)
        preflight = SourceMapFollowthroughDispatchTransactionPreflightManager().review(
            SourceMapFollowthroughDispatchTransactionPreflightSpec.from_context(
                {
                    "source_map_followthrough_dispatch_transaction_preflight": True,
                    "source_map_followthrough_dispatch_approval_plan": approval_descriptor,
                    "source_map_followthrough_dispatch_approval_record": approval_record,
                    "expected_consumer": "debugger",
                    "expected_dispatch_surface": "source-map-debugger-execution-result",
                    "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                    "reviewer": "analyst",
                }
            )
        ).descriptor
        preflight_digest = hashlib.sha256(json.dumps(preflight, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        transaction_preflight_id = f"source-map-followthrough-dispatch-transaction-preflight:{preflight_digest[:16]}"
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-journal.v1",
            "status": "written",
            "journal_written": True,
            "transaction_started": True,
            "journal_id": "source-map-followthrough-dispatch-transaction-journal:test",
            "transaction_preflight_id": transaction_preflight_id,
            "approval_record_id": preflight["approval_record_id"],
            "approval_plan_id": preflight["approval_plan_id"],
            "transaction_plan_id": preflight["transaction_plan_id"],
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "transaction_preflight_digest_sha256": preflight_digest,
            "journal_summary": {
                "entry_count": 2,
                "planned_entry_count": 2,
                "transaction_started": True,
                "journal_written": True,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "requires_bounded_dispatch_gate_followup": True,
            },
            "dispatch_input_gates": {
                "ready_to_dispatch_now": False,
                "approval_record_verified": True,
                "transaction_plan_verified": True,
                "transaction_started": True,
                "journal_written": True,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "debugger_executed": False,
                "source_logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "requires_bounded_dispatch_gate": True,
                "requires_explicit_dispatch_review": True,
            },
            "blockers": [],
            "side_effect_policy": {
                "transaction_journal_writer": True,
                "files_mutated": True,
                "artifacts_written": True,
                "writes_transaction_journal": True,
                "transaction_started": True,
                "journal_written": True,
                "ready_to_dispatch_now": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "debugger_execution_performed": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    def test_source_map_followthrough_dispatch_bounded_executor_gate_reviews_written_journal_without_dispatch(self) -> None:
        journal = self._ready_transaction_journal()
        journal_digest = hashlib.sha256(json.dumps(journal, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapFollowthroughDispatchBoundedExecutorGateSpec.from_context(
            {
                "source_map_followthrough_dispatch_bounded_executor_gate": True,
                "source_map_followthrough_dispatch_transaction_journal": journal,
                "expected_journal_id": journal["journal_id"],
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "expected_journal_digest_sha256": journal_digest,
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughDispatchBoundedExecutorGateManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-bounded-executor-gate.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["read_only"])
        self.assertTrue(descriptor["bounded_executor_gate_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertEqual(descriptor["required_result_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertTrue(descriptor["transaction_journal_verified"])
        self.assertTrue(descriptor["bounded_executor_gate_ready_for_review"])
        self.assertTrue(descriptor["ready_for_dispatcher_handoff_review"])
        self.assertFalse(descriptor["ready_to_dispatch_now"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["will_invoke_dispatch_target"])
        self.assertFalse(descriptor["will_invoke_next_action"])
        self.assertFalse(descriptor["will_run_apply_preflight"])
        self.assertFalse(descriptor["will_execute_debugger"])
        self.assertFalse(descriptor["will_install_source_logpoint"])
        self.assertFalse(descriptor["will_install_hook"])
        self.assertFalse(descriptor["will_run_rebuild"])
        self.assertEqual(descriptor["bounded_dispatch_input"]["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-bounded-input.v1")
        self.assertTrue(descriptor["bounded_dispatch_input"]["requires_explicit_dispatcher_handoff_review"])
        self.assertEqual(descriptor["future_dispatcher_contract"]["dispatcher_name"], "dispatch_source_map_followthrough_next_action")
        self.assertFalse(descriptor["future_dispatcher_contract"]["implemented"])
        self.assertEqual(descriptor["future_dispatcher_contract"]["result_artifact"], "workspace/source-map-followthrough-dispatcher-handoff.json")
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_followthrough_dispatcher_handoff")

    def test_source_map_followthrough_dispatch_bounded_executor_gate_blocks_bad_journal(self) -> None:
        journal = self._ready_transaction_journal()
        journal["journal_written"] = False
        journal["dispatch_input_gates"]["ready_to_dispatch_now"] = True
        journal["side_effect_policy"]["cdp_command_sent"] = True
        spec = SourceMapFollowthroughDispatchBoundedExecutorGateSpec.from_context(
            {
                "source_map_followthrough_dispatch_bounded_executor_gate": True,
                "source_map_followthrough_dispatch_transaction_journal": journal,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapFollowthroughDispatchBoundedExecutorGateManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["bounded_executor_gate_ready_for_review"])
        self.assertIn("transaction_journal_written", result.descriptor["blockers"])
        self.assertIn("journal_not_ready_to_dispatch_now", result.descriptor["blockers"])
        self.assertIn("journal_no_runtime_side_effects", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "resolve_source_map_followthrough_dispatch_bounded_executor_gate_blockers")


class SourceMapFollowthroughDispatcherHandoffManagerTests(unittest.TestCase):
    def _ready_bounded_gate(self) -> dict[str, object]:
        journal = SourceMapFollowthroughDispatchBoundedExecutorGateManagerTests()._ready_transaction_journal()
        result = SourceMapFollowthroughDispatchBoundedExecutorGateManager().review(
            SourceMapFollowthroughDispatchBoundedExecutorGateSpec.from_context(
                {
                    "source_map_followthrough_dispatch_bounded_executor_gate": True,
                    "source_map_followthrough_dispatch_transaction_journal": journal,
                    "expected_consumer": "debugger",
                    "expected_dispatch_surface": "source-map-debugger-execution-result",
                    "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                    "reviewer": "analyst",
                }
            )
        )
        self.assertEqual(result.status, "ready_for_review")
        return result.descriptor

    def test_source_map_followthrough_dispatcher_handoff_reviews_bounded_gate_without_dispatch(self) -> None:
        gate = self._ready_bounded_gate()
        gate_digest = hashlib.sha256(json.dumps(gate, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapFollowthroughDispatcherHandoffSpec.from_context(
            {
                "source_map_followthrough_dispatcher_handoff": True,
                "source_map_followthrough_dispatch_bounded_executor_gate": gate,
                "expected_gate_digest_sha256": gate_digest,
                "expected_journal_id": gate["journal_id"],
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughDispatcherHandoffManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-dispatcher-handoff.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["read_only"])
        self.assertTrue(descriptor["dispatcher_handoff_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertEqual(descriptor["required_result_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertTrue(descriptor["bounded_gate_verified"])
        self.assertTrue(descriptor["dispatcher_handoff_ready_for_review"])
        self.assertTrue(descriptor["ready_for_explicit_dispatch_review"])
        self.assertTrue(descriptor["ready_for_selected_executor_review"])
        self.assertFalse(descriptor["ready_to_dispatch_now"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["dispatcher_invoked"])
        self.assertFalse(descriptor["dispatch_target_invoked"])
        self.assertFalse(descriptor["executor_invoked"])
        self.assertFalse(descriptor["apply_preflight_invoked"])
        self.assertFalse(descriptor["will_invoke_dispatcher"])
        self.assertFalse(descriptor["will_invoke_selected_executor"])
        self.assertFalse(descriptor["will_run_apply_preflight"])
        self.assertEqual(descriptor["dispatcher_handoff"]["schema_version"], "reverse-deepagent.source-map-followthrough-dispatcher-handoff-input.v1")
        self.assertEqual(descriptor["dispatcher_handoff"]["dispatcher_name"], "dispatch_source_map_followthrough_next_action")
        self.assertTrue(descriptor["dispatcher_handoff"]["requires_selected_executor_apply_preflight"])
        self.assertEqual(descriptor["selected_executor_review_contract"]["selected_executor_apply_preflight_artifact"], "workspace/source-map-selected-executor-apply-preflight.json")
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_followthrough_dispatcher_apply_preflight")

    def test_source_map_followthrough_dispatcher_handoff_blocks_bad_gate(self) -> None:
        gate = self._ready_bounded_gate()
        gate["bounded_executor_gate_ready_for_review"] = False
        gate["ready_to_dispatch_now"] = True
        gate["side_effect_policy"]["browser_started"] = True
        spec = SourceMapFollowthroughDispatcherHandoffSpec.from_context(
            {
                "source_map_followthrough_dispatcher_handoff": True,
                "source_map_followthrough_dispatch_bounded_executor_gate": gate,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapFollowthroughDispatcherHandoffManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["dispatcher_handoff_ready_for_review"])
        self.assertIn("bounded_gate_ready", result.descriptor["blockers"])
        self.assertIn("source_gate_not_ready_to_dispatch_now", result.descriptor["blockers"])
        self.assertIn("bounded_gate_no_runtime_side_effects", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "resolve_source_map_followthrough_dispatcher_handoff_blockers")


class SourceMapFollowthroughDispatcherApplyPreflightManagerTests(unittest.TestCase):
    def _ready_handoff(self) -> dict[str, object]:
        gate = SourceMapFollowthroughDispatcherHandoffManagerTests()._ready_bounded_gate()
        result = SourceMapFollowthroughDispatcherHandoffManager().review(
            SourceMapFollowthroughDispatcherHandoffSpec.from_context(
                {
                    "source_map_followthrough_dispatcher_handoff": True,
                    "source_map_followthrough_dispatch_bounded_executor_gate": gate,
                    "expected_consumer": "debugger",
                    "expected_dispatch_surface": "source-map-debugger-execution-result",
                    "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                    "reviewer": "analyst",
                }
            )
        )
        self.assertEqual(result.status, "ready_for_review")
        return result.descriptor

    def test_source_map_followthrough_dispatcher_apply_preflight_reviews_handoff_without_dispatch(self) -> None:
        handoff = self._ready_handoff()
        handoff_digest = hashlib.sha256(json.dumps(handoff, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapFollowthroughDispatcherApplyPreflightSpec.from_context(
            {
                "source_map_followthrough_dispatcher_apply_preflight": True,
                "source_map_followthrough_dispatcher_handoff": handoff,
                "expected_handoff_digest_sha256": handoff_digest,
                "expected_journal_id": handoff["journal_id"],
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "reviewer": "analyst",
            }
        )

        result = SourceMapFollowthroughDispatcherApplyPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["read_only"])
        self.assertTrue(descriptor["preflight_only"])
        self.assertTrue(descriptor["dispatcher_apply_preflight_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertEqual(descriptor["required_result_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertTrue(descriptor["handoff_verified"])
        self.assertTrue(descriptor["dispatcher_apply_preflight_ready_for_review"])
        self.assertTrue(descriptor["ready_for_explicit_dispatcher_mvp_review"])
        self.assertFalse(descriptor["ready_to_dispatch_now"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["dispatcher_invoked"])
        self.assertFalse(descriptor["dispatch_target_invoked"])
        self.assertFalse(descriptor["executor_invoked"])
        self.assertFalse(descriptor["selected_executor_apply_preflight_invoked"])
        self.assertFalse(descriptor["will_invoke_dispatcher"])
        self.assertFalse(descriptor["will_invoke_selected_executor"])
        self.assertFalse(descriptor["will_run_selected_executor_apply_preflight"])
        self.assertEqual(descriptor["dispatcher_apply_preflight"]["schema_version"], "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight-input.v1")
        self.assertEqual(descriptor["dispatcher_apply_preflight"]["dispatcher_name"], "dispatch_source_map_followthrough_next_action")
        self.assertEqual(descriptor["dispatcher_apply_preflight"]["selected_executor_apply_preflight_artifact"], "workspace/source-map-selected-executor-apply-preflight.json")
        self.assertEqual(descriptor["future_dispatcher_mvp_contract"]["schema_version"], "reverse-deepagent.source-map-followthrough-dispatcher-mvp-contract.v1")
        self.assertFalse(descriptor["future_dispatcher_mvp_contract"]["implemented"])
        self.assertEqual(descriptor["future_dispatcher_mvp_contract"]["input_artifact"], "workspace/source-map-followthrough-dispatcher-apply-preflight.json")
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_followthrough_dispatcher_mvp")

    def test_source_map_followthrough_dispatcher_apply_preflight_blocks_bad_handoff(self) -> None:
        handoff = self._ready_handoff()
        handoff["dispatcher_handoff_ready_for_review"] = False
        handoff["ready_to_dispatch_now"] = True
        handoff["side_effect_policy"]["cdp_command_sent"] = True
        spec = SourceMapFollowthroughDispatcherApplyPreflightSpec.from_context(
            {
                "source_map_followthrough_dispatcher_apply_preflight": True,
                "source_map_followthrough_dispatcher_handoff": handoff,
                "expected_consumer": "debugger",
            }
        )

        result = SourceMapFollowthroughDispatcherApplyPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.descriptor["dispatcher_apply_preflight_ready_for_review"])
        self.assertIn("dispatcher_handoff_ready", result.descriptor["blockers"])
        self.assertIn("source_handoff_not_ready_to_dispatch_now", result.descriptor["blockers"])
        self.assertIn("dispatcher_handoff_no_runtime_side_effects", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "resolve_source_map_followthrough_dispatcher_apply_preflight_blockers")


class SourceMapFollowthroughDispatcherManagerTests(unittest.TestCase):
    def _ready_apply_preflight(self) -> dict[str, object]:
        handoff = SourceMapFollowthroughDispatcherApplyPreflightManagerTests()._ready_handoff()
        result = SourceMapFollowthroughDispatcherApplyPreflightManager().review(
            SourceMapFollowthroughDispatcherApplyPreflightSpec.from_context(
                {
                    "source_map_followthrough_dispatcher_apply_preflight": True,
                    "source_map_followthrough_dispatcher_handoff": handoff,
                    "expected_consumer": "debugger",
                    "expected_dispatch_surface": "source-map-debugger-execution-result",
                    "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                    "reviewer": "analyst",
                }
            )
        )
        self.assertEqual(result.status, "ready_for_review")
        return result.descriptor

    def test_source_map_followthrough_dispatcher_records_reviewed_decision_without_executor(self) -> None:
        apply_preflight = self._ready_apply_preflight()
        apply_preflight_digest = hashlib.sha256(json.dumps(apply_preflight, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        spec = SourceMapFollowthroughDispatcherResultSpec.from_context(
            {
                "source_map_followthrough_dispatcher_result": True,
                "source_map_followthrough_dispatcher_apply_preflight": apply_preflight,
                "mode": "apply",
                "write_result": True,
                "review_approved": True,
                "approve_dispatcher_mvp": True,
                "reviewer": "analyst",
                "expected_apply_preflight_digest_sha256": apply_preflight_digest,
                "expected_journal_id": apply_preflight["journal_id"],
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
            }
        )

        result = SourceMapFollowthroughDispatcherManager().dispatch(spec)

        self.assertEqual(result.status, "dispatched")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.source-map-followthrough-dispatcher-result.v1")
        self.assertTrue(descriptor["explicit_review_only"])
        self.assertTrue(descriptor["dispatcher_mvp"])
        self.assertTrue(descriptor["decision_record_only"])
        self.assertEqual(descriptor["selected_consumer"], "debugger")
        self.assertEqual(descriptor["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertEqual(descriptor["required_result_artifact"], "workspace/source-map-debugger-execution-result.json")
        self.assertTrue(descriptor["apply_preflight_verified"])
        self.assertTrue(descriptor["dispatcher_decision_recorded"])
        self.assertTrue(descriptor["dispatcher_mvp_invoked"])
        self.assertFalse(descriptor["dispatcher_invoked"])
        self.assertFalse(descriptor["dispatch_target_invoked"])
        self.assertFalse(descriptor["executor_invoked"])
        self.assertFalse(descriptor["selected_executor_invoked"])
        self.assertFalse(descriptor["selected_executor_apply_preflight_invoked"])
        self.assertFalse(descriptor["ready_to_execute_selected_executor_now"])
        self.assertTrue(descriptor["requires_selected_executor_apply_preflight"])
        self.assertTrue(descriptor["requires_separate_selected_executor_apply_preflight"])
        self.assertTrue(descriptor["requires_separate_selected_executor_execution"])
        self.assertEqual(descriptor["dispatch_decision"]["schema_version"], "reverse-deepagent.source-map-followthrough-dispatcher-decision.v1")
        self.assertEqual(descriptor["dispatch_decision"]["next_review_action"], "review_source_map_selected_executor_apply_preflight")
        self.assertEqual(descriptor["selected_executor_apply_preflight_artifact"], "workspace/source-map-selected-executor-apply-preflight.json")
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_source_map_selected_executor_apply_preflight")

    def test_source_map_followthrough_dispatcher_requires_review_and_blocks_bad_preflight(self) -> None:
        apply_preflight = self._ready_apply_preflight()
        review_spec = SourceMapFollowthroughDispatcherResultSpec.from_context(
            {
                "source_map_followthrough_dispatcher_result": True,
                "source_map_followthrough_dispatcher_apply_preflight": apply_preflight,
                "mode": "apply",
                "write_result": True,
            }
        )

        review_result = SourceMapFollowthroughDispatcherManager().dispatch(review_spec)

        self.assertEqual(review_result.status, "review_required")
        self.assertFalse(review_result.descriptor["dispatcher_decision_recorded"])
        self.assertIn("review_approved", review_result.descriptor["approval_blockers"])
        self.assertIn("approve_dispatcher_mvp", review_result.descriptor["approval_blockers"])
        self.assertIn("reviewer_present", review_result.descriptor["approval_blockers"])
        self.assertEqual(review_result.descriptor["next_action"], "approve_source_map_followthrough_dispatcher_mvp")

        bad_preflight = self._ready_apply_preflight()
        bad_preflight["dispatcher_apply_preflight_ready_for_review"] = False
        bad_preflight["side_effect_policy"]["browser_started"] = True
        blocked_spec = SourceMapFollowthroughDispatcherResultSpec.from_context(
            {
                "source_map_followthrough_dispatcher_result": True,
                "source_map_followthrough_dispatcher_apply_preflight": bad_preflight,
                "mode": "apply",
                "write_result": True,
                "review_approved": True,
                "approve_dispatcher_mvp": True,
                "reviewer": "analyst",
            }
        )

        blocked_result = SourceMapFollowthroughDispatcherManager().dispatch(blocked_spec)

        self.assertEqual(blocked_result.status, "blocked")
        self.assertFalse(blocked_result.descriptor["apply_preflight_verified"])
        self.assertFalse(blocked_result.descriptor["dispatcher_decision_recorded"])
        self.assertIn("dispatcher_apply_preflight_ready", blocked_result.descriptor["blockers"])
        self.assertIn("dispatcher_apply_preflight_no_runtime_side_effects", blocked_result.descriptor["blockers"])
        self.assertEqual(blocked_result.descriptor["next_action"], "resolve_source_map_followthrough_dispatcher_result_blockers")


class SourceMapRemapperTests(unittest.TestCase):
    def test_location_from_offset_uses_generated_bundle_position(self) -> None:
        source = "alpha\nbeta\ngamma"
        location = SourceMapRemapper.location_from_offset(source, 6)

        self.assertEqual(location.line_number, 1)
        self.assertEqual(location.column_number, 0)
        self.assertEqual(location.strategy, "bundle_offset")
        self.assertEqual(location.metadata["offset"], 6)
        self.assertEqual(location.metadata["source_size"], len(source))

    def test_location_from_source_map_matches_exact_generated_mapping(self) -> None:
        source_map = {"version": 3, "sources": ["src/app.js"], "names": [], "mappings": "AAAA"}

        location = SourceMapRemapper.location_from_source_map(
            source_map,
            original_source="src/app.js",
            original_line_number=0,
            original_column_number=0,
        )

        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.line_number, 0)
        self.assertEqual(location.column_number, 0)
        self.assertEqual(location.source, "src/app.js")
        self.assertEqual(location.original_line_number, 0)
        self.assertEqual(location.original_column_number, 0)
        self.assertEqual(location.strategy, "source_map_exact")

    def test_location_from_source_map_resolves_source_root(self) -> None:
        source_map = {"version": 3, "sourceRoot": "/src", "sources": ["app.js"], "names": [], "mappings": "AAAA"}

        location = SourceMapRemapper.location_from_source_map(
            source_map,
            original_source="/src/app.js",
            original_line_number=0,
            original_column_number=0,
        )

        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.line_number, 0)
        self.assertEqual(location.column_number, 0)
        self.assertEqual(location.source, "/src/app.js")
        self.assertEqual(location.metadata["sourceRoot"], "/src")

    def test_location_from_source_map_records_name_metadata(self) -> None:
        source_map = {
            "version": 3,
            "sources": ["src/app.js"],
            "names": ["buildSign"],
            "mappings": encode_vlq_segment([0, 0, 0, 0, 0]),
        }

        location = SourceMapRemapper.location_from_source_map(
            source_map,
            original_source="src/app.js",
            original_line_number=0,
            original_column_number=0,
        )

        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.strategy, "source_map_exact")
        self.assertEqual(location.metadata["name_index"], 0)
        self.assertEqual(location.metadata["name"], "buildSign")
        self.assertEqual(location.metadata["names_count"], 1)

    def test_location_from_source_map_matches_url_equivalent_sources(self) -> None:
        source_map = {
            "version": 3,
            "sourceRoot": "webpack://demo",
            "sources": ["./src/../src/app.ts?cache=abc#ignored"],
            "names": [],
            "mappings": "AAAA",
        }

        location = SourceMapRemapper.location_from_source_map(
            source_map,
            original_source="webpack://demo/src/app.ts#L10",
            original_line_number=0,
            original_column_number=0,
        )

        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.line_number, 0)
        self.assertEqual(location.column_number, 0)
        self.assertEqual(location.source, "webpack://demo/./src/../src/app.ts?cache=abc#ignored")
        self.assertEqual(location.metadata["source_match"]["normalized_match"], "webpack://demo/src/app.ts")
        self.assertTrue(location.metadata["source_match"]["url_equivalence"])

    def test_location_from_source_map_uses_greatest_lower_bound_bias(self) -> None:
        source_map = {
            "version": 3,
            "sources": ["src/app.js"],
            "names": [],
            "mappings": f"{encode_vlq_segment([0, 0, 0, 0])},{encode_vlq_segment([10, 0, 0, 5])}",
        }

        location = SourceMapRemapper.location_from_source_map(
            source_map,
            original_source="src/app.js",
            original_line_number=0,
            original_column_number=7,
        )

        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.line_number, 0)
        self.assertEqual(location.column_number, 10)
        self.assertEqual(location.strategy, "source_map_bias_glb")
        self.assertEqual(location.metadata["matched_original_column_number"], 5)
        self.assertEqual(location.metadata["bias"], "greatest_lower_bound")

    def test_location_from_indexed_source_map_offsets_generated_location(self) -> None:
        source_map = {
            "version": 3,
            "sections": [
                {
                    "offset": {"line": 2, "column": 4},
                    "map": {"version": 3, "sources": ["src/app.js"], "names": [], "mappings": "AAAA"},
                }
            ],
        }

        location = SourceMapRemapper.location_from_source_map(
            source_map,
            original_source="src/app.js",
            original_line_number=0,
            original_column_number=0,
        )

        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.line_number, 2)
        self.assertEqual(location.column_number, 4)
        self.assertEqual(location.strategy, "source_map_indexed_exact")
        self.assertEqual(location.metadata["section_index"], 0)
        self.assertEqual(location.metadata["section_offset_line"], 2)
        self.assertEqual(location.metadata["section_offset_column"], 4)

    def test_location_from_nested_indexed_source_map_tracks_section_stack(self) -> None:
        source_map = {
            "version": 3,
            "sections": [
                {
                    "offset": {"line": 3, "column": 2},
                    "map": {
                        "version": 3,
                        "sections": [
                            {
                                "offset": {"line": 1, "column": 5},
                                "map": {"version": 3, "sources": ["src/app.js"], "names": [], "mappings": "AAAA"},
                            }
                        ],
                    },
                }
            ],
        }

        location = SourceMapRemapper.location_from_source_map(
            source_map,
            original_source="src/app.js",
            original_line_number=0,
            original_column_number=0,
        )

        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.line_number, 4)
        self.assertEqual(location.column_number, 5)
        self.assertEqual(location.strategy, "source_map_indexed_exact")
        self.assertEqual(location.metadata["indexed_section_depth"], 2)
        self.assertEqual([item["section_index"] for item in location.metadata["section_stack"]], [0, 0])
        self.assertEqual([item["offset_line"] for item in location.metadata["section_stack"]], [3, 1])
        self.assertEqual([item["offset_column"] for item in location.metadata["section_stack"]], [2, 5])

    def test_resolve_from_context_prefers_bundle_offset_over_source_map(self) -> None:
        context = {
            "bundle_source": "alpha\nbeta",
            "bundle_offset": 6,
            "source_map": {"version": 3, "sources": ["src/app.js"], "names": [], "mappings": "AAAA"},
            "original_source": "src/app.js",
            "original_line": 0,
            "original_column": 0,
        }

        location = SourceMapRemapper.resolve_from_context(context)

        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.strategy, "bundle_offset")
        self.assertEqual(location.line_number, 1)
        self.assertEqual(location.column_number, 0)


if __name__ == "__main__":
    unittest.main()
