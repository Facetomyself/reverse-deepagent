import unittest

from reverse_deepagent.browser.source_maps import SourceMapRemapper


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
