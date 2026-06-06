import unittest

from reverse_deepagent.browser.source_maps import (
    BundlerSymbolScopeManager,
    BundlerSymbolScopeSpec,
    SourceMapFetchManager,
    SourceMapFetchSpec,
    SourceMapLookupManager,
    SourceMapLookupSpec,
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
