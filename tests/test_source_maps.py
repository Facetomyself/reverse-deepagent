import hashlib
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
    SourceMapFollowthroughReviewManager,
    SourceMapFollowthroughReviewSpec,
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
