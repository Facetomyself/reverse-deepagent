from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

BASE64_VLQ_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
BASE64_VLQ_VALUES = {char: index for index, char in enumerate(BASE64_VLQ_CHARS)}


@dataclass(slots=True)
class GeneratedLocation:
    line_number: int
    column_number: int
    source: str | None = None
    original_line_number: int | None = None
    original_column_number: int | None = None
    strategy: str = "direct"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "column_number": self.column_number,
            "source": self.source,
            "original_line_number": self.original_line_number,
            "original_column_number": self.original_column_number,
            "strategy": self.strategy,
            "metadata": self.metadata,
        }


class SourceMapRemapper:
    """Small Source Map v3 and generated-bundle offset remapper.

    The resolver intentionally implements the stable baseline used by
    source-logpoint routing: generated bundle character offsets, flat Source
    Map v3 mapping lookup, sourceRoot-aware source matching, GLB bias fallback,
    indexed source-map sections with generated offsets, source-map ``names``
    metadata, URL-like source equivalence, and nested indexed sections. External
    Source Map URL fetching is handled separately by ``SourceMapFetchManager``
    and remains explicit, review-gated, and credentialless.
    """

    @classmethod
    def resolve_from_context(cls, context: dict[str, Any] | None = None) -> GeneratedLocation | None:
        context = context or {}
        offset = context.get("bundle_offset", context.get("bundleOffset", context.get("generated_offset", context.get("generatedOffset"))))
        source_text = context.get("bundle_source", context.get("bundleSource", context.get("script_source", context.get("scriptSource"))))
        if offset is not None and source_text is not None:
            return cls.location_from_offset(str(source_text), int(offset))

        source_map_payload = context.get("source_map", context.get("sourceMap"))
        original_source = context.get("original_source", context.get("originalSource", context.get("source")))
        original_line = context.get(
            "original_line",
            context.get("originalLine", context.get("original_line_number", context.get("originalLineNumber"))),
        )
        if source_map_payload is not None and original_source is not None and original_line is not None:
            original_column = context.get(
                "original_column",
                context.get("originalColumn", context.get("original_column_number", context.get("originalColumnNumber", 0))),
            )
            line_base = int(context.get("original_line_base", context.get("originalLineBase", 0)) or 0)
            column_base = int(context.get("original_column_base", context.get("originalColumnBase", 0)) or 0)
            return cls.location_from_source_map(
                source_map_payload,
                original_source=str(original_source),
                original_line_number=int(original_line) - line_base,
                original_column_number=int(original_column or 0) - column_base,
                bias=str(context.get("source_map_bias", context.get("sourceMapBias", "greatest_lower_bound"))),
            )
        return None

    @staticmethod
    def location_from_offset(source: str, offset: int) -> GeneratedLocation:
        clamped = max(0, min(offset, len(source)))
        line = 0
        line_start = 0
        for index, char in enumerate(source[:clamped]):
            if char == "\n":
                line += 1
                line_start = index + 1
        column = clamped - line_start
        return GeneratedLocation(
            line_number=line,
            column_number=column,
            strategy="bundle_offset",
            metadata={"offset": offset, "clamped_offset": clamped, "source_size": len(source)},
        )

    @classmethod
    def location_from_source_map(
        cls,
        source_map_payload: str | dict[str, Any],
        *,
        original_source: str,
        original_line_number: int,
        original_column_number: int = 0,
        bias: str = "greatest_lower_bound",
    ) -> GeneratedLocation | None:
        source_map = cls._coerce_source_map(source_map_payload)
        sections = source_map.get("sections")
        if isinstance(sections, list):
            return cls._location_from_indexed_source_map(
                source_map,
                original_source=original_source,
                original_line_number=original_line_number,
                original_column_number=original_column_number,
                bias=bias,
            )
        return cls._location_from_flat_source_map(
            source_map,
            original_source=original_source,
            original_line_number=original_line_number,
            original_column_number=original_column_number,
            bias=bias,
        )

    @classmethod
    def location_from_generated(
        cls,
        source_map_payload: str | dict[str, Any],
        *,
        generated_line_number: int,
        generated_column_number: int = 0,
        bias: str = "greatest_lower_bound",
    ) -> GeneratedLocation | None:
        """Map a generated bundle position back to an original source position."""

        source_map = cls._coerce_source_map(source_map_payload)
        sections = source_map.get("sections")
        if isinstance(sections, list):
            return cls._location_from_generated_indexed_source_map(
                source_map,
                generated_line_number=generated_line_number,
                generated_column_number=generated_column_number,
                bias=bias,
            )
        return cls._location_from_generated_flat_source_map(
            source_map,
            generated_line_number=generated_line_number,
            generated_column_number=generated_column_number,
            bias=bias,
        )

    @classmethod
    def _location_from_flat_source_map(
        cls,
        source_map: dict[str, Any],
        *,
        original_source: str,
        original_line_number: int,
        original_column_number: int,
        bias: str,
    ) -> GeneratedLocation | None:
        sources = source_map.get("sources", []) if isinstance(source_map.get("sources"), list) else []
        source_index, resolved_source, source_match = cls._find_source_index(
            sources,
            original_source=original_source,
            source_root=str(source_map.get("sourceRoot") or ""),
        )
        if source_index < 0:
            return None
        exact_match: dict[str, Any] | None = None
        bias_match: dict[str, Any] | None = None
        for mapping in cls.iter_mappings(source_map):
            if (
                mapping.get("source_index") == source_index
                and mapping.get("original_line_number") == original_line_number
                and mapping.get("original_column_number") == original_column_number
            ):
                exact_match = mapping
                break
            if (
                mapping.get("source_index") == source_index
                and mapping.get("original_line_number") == original_line_number
                and isinstance(mapping.get("original_column_number"), int)
                and int(mapping["original_column_number"]) <= original_column_number
            ):
                if bias_match is None or int(mapping["original_column_number"]) > int(bias_match.get("original_column_number", -1)):
                    bias_match = mapping
        if exact_match is not None:
            return cls._location_from_mapping(
                exact_match,
                source=resolved_source,
                original_line_number=original_line_number,
                original_column_number=original_column_number,
                strategy="source_map_exact",
                source_index=source_index,
                source_match=source_match,
                source_map=source_map,
            )
        normalized_bias = bias.strip().replace("-", "_").lower()
        if normalized_bias in {"glb", "greatest_lower_bound", "lower_bound"} and bias_match is not None:
            return cls._location_from_mapping(
                bias_match,
                source=resolved_source,
                original_line_number=original_line_number,
                original_column_number=original_column_number,
                strategy="source_map_bias_glb",
                source_index=source_index,
                source_match=source_match,
                source_map=source_map,
                extra_metadata={
                    "matched_original_column_number": bias_match.get("original_column_number"),
                    "bias": "greatest_lower_bound",
                },
            )
        return None

    @classmethod
    def _location_from_generated_flat_source_map(
        cls,
        source_map: dict[str, Any],
        *,
        generated_line_number: int,
        generated_column_number: int,
        bias: str,
    ) -> GeneratedLocation | None:
        exact_match: dict[str, Any] | None = None
        bias_match: dict[str, Any] | None = None
        for mapping in cls.iter_mappings(source_map):
            if not cls._mapping_has_original_location(mapping):
                continue
            if (
                mapping.get("generated_line_number") == generated_line_number
                and mapping.get("generated_column_number") == generated_column_number
            ):
                exact_match = mapping
                break
            if (
                mapping.get("generated_line_number") == generated_line_number
                and isinstance(mapping.get("generated_column_number"), int)
                and int(mapping["generated_column_number"]) <= generated_column_number
            ):
                if bias_match is None or int(mapping["generated_column_number"]) > int(bias_match.get("generated_column_number", -1)):
                    bias_match = mapping
        if exact_match is not None:
            return cls._original_location_from_mapping(
                exact_match,
                source_map=source_map,
                requested_generated_line_number=generated_line_number,
                requested_generated_column_number=generated_column_number,
                strategy="source_map_generated_exact",
            )
        normalized_bias = bias.strip().replace("-", "_").lower()
        if normalized_bias in {"glb", "greatest_lower_bound", "lower_bound"} and bias_match is not None:
            return cls._original_location_from_mapping(
                bias_match,
                source_map=source_map,
                requested_generated_line_number=generated_line_number,
                requested_generated_column_number=generated_column_number,
                strategy="source_map_generated_bias_glb",
                extra_metadata={
                    "matched_generated_line_number": bias_match.get("generated_line_number"),
                    "matched_generated_column_number": bias_match.get("generated_column_number"),
                    "bias": "greatest_lower_bound",
                },
            )
        return None

    @classmethod
    def _location_from_indexed_source_map(
        cls,
        source_map: dict[str, Any],
        *,
        original_source: str,
        original_line_number: int,
        original_column_number: int,
        bias: str,
    ) -> GeneratedLocation | None:
        sections = source_map.get("sections")
        if not isinstance(sections, list):
            return None
        for index, section in enumerate(sections):
            if not isinstance(section, dict) or not isinstance(section.get("map"), dict):
                continue
            offset = section.get("offset") if isinstance(section.get("offset"), dict) else {}
            offset_line = int(offset.get("line", 0) or 0)
            offset_column = int(offset.get("column", 0) or 0)
            child = cls.location_from_source_map(
                section["map"],
                original_source=original_source,
                original_line_number=original_line_number,
                original_column_number=original_column_number,
                bias=bias,
            )
            if child is None:
                continue
            generated_line = child.line_number + offset_line
            generated_column = child.column_number + offset_column if child.line_number == 0 else child.column_number
            metadata = dict(child.metadata)
            metadata.update(
                {
                    "section_index": index,
                    "section_offset_line": offset_line,
                    "section_offset_column": offset_column,
                    "child_strategy": child.strategy,
                }
            )
            section_entry = {
                "section_index": index,
                "offset_line": offset_line,
                "offset_column": offset_column,
                "child_strategy": child.strategy,
            }
            child_stack = metadata.get("section_stack") if isinstance(metadata.get("section_stack"), list) else []
            metadata["section_stack"] = [section_entry, *child_stack]
            metadata["indexed_section_depth"] = len(metadata["section_stack"])
            strategy = "source_map_indexed_exact" if "exact" in child.strategy else "source_map_indexed_bias_glb"
            return GeneratedLocation(
                line_number=generated_line,
                column_number=generated_column,
                source=child.source,
                original_line_number=original_line_number,
                original_column_number=original_column_number,
                strategy=strategy,
                metadata=metadata,
            )
        return None

    @classmethod
    def _location_from_generated_indexed_source_map(
        cls,
        source_map: dict[str, Any],
        *,
        generated_line_number: int,
        generated_column_number: int,
        bias: str,
    ) -> GeneratedLocation | None:
        sections = source_map.get("sections")
        if not isinstance(sections, list):
            return None
        candidates: list[tuple[int, dict[str, Any], int, int]] = []
        for index, section in enumerate(sections):
            if not isinstance(section, dict) or not isinstance(section.get("map"), dict):
                continue
            offset = section.get("offset") if isinstance(section.get("offset"), dict) else {}
            offset_line = int(offset.get("line", 0) or 0)
            offset_column = int(offset.get("column", 0) or 0)
            if cls._section_offset_before_or_at(offset_line, offset_column, generated_line_number, generated_column_number):
                candidates.append((index, section, offset_line, offset_column))
        for index, section, offset_line, offset_column in reversed(candidates):
            local_line = generated_line_number - offset_line
            local_column = generated_column_number - offset_column if local_line == 0 else generated_column_number
            if local_line < 0 or local_column < 0:
                continue
            child = cls.location_from_generated(
                section["map"],
                generated_line_number=local_line,
                generated_column_number=local_column,
                bias=bias,
            )
            if child is None:
                continue
            metadata = dict(child.metadata)
            metadata.update(
                {
                    "section_index": index,
                    "section_offset_line": offset_line,
                    "section_offset_column": offset_column,
                    "child_strategy": child.strategy,
                    "requested_global_generated_line_number": generated_line_number,
                    "requested_global_generated_column_number": generated_column_number,
                    "local_generated_line_number": local_line,
                    "local_generated_column_number": local_column,
                }
            )
            section_entry = {
                "section_index": index,
                "offset_line": offset_line,
                "offset_column": offset_column,
                "child_strategy": child.strategy,
            }
            child_stack = metadata.get("section_stack") if isinstance(metadata.get("section_stack"), list) else []
            metadata["section_stack"] = [section_entry, *child_stack]
            metadata["indexed_section_depth"] = len(metadata["section_stack"])
            strategy = "source_map_generated_indexed_exact" if "exact" in child.strategy else "source_map_generated_indexed_bias_glb"
            return GeneratedLocation(
                line_number=generated_line_number,
                column_number=generated_column_number,
                source=child.source,
                original_line_number=child.original_line_number,
                original_column_number=child.original_column_number,
                strategy=strategy,
                metadata=metadata,
            )
        return None

    @staticmethod
    def _location_from_mapping(
        mapping: dict[str, Any],
        *,
        source: str,
        original_line_number: int,
        original_column_number: int,
        strategy: str,
        source_index: int,
        source_match: dict[str, Any],
        source_map: dict[str, Any],
        extra_metadata: dict[str, Any] | None = None,
    ) -> GeneratedLocation:
        names = source_map.get("names", []) if isinstance(source_map.get("names"), list) else []
        metadata = {
            "source_index": source_index,
            "sources_count": len(source_map.get("sources", []) if isinstance(source_map.get("sources"), list) else []),
            "names_count": len(names),
            "source_match": source_match,
        }
        name_index = mapping.get("name_index")
        if isinstance(name_index, int):
            metadata["name_index"] = name_index
            if 0 <= name_index < len(names):
                metadata["name"] = str(names[name_index])
        if source_map.get("sourceRoot"):
            metadata["sourceRoot"] = source_map.get("sourceRoot")
        if extra_metadata:
            metadata.update(extra_metadata)
        return GeneratedLocation(
            line_number=int(mapping["generated_line_number"]),
            column_number=int(mapping["generated_column_number"]),
            source=source,
            original_line_number=original_line_number,
            original_column_number=original_column_number,
            strategy=strategy,
            metadata=metadata,
        )

    @classmethod
    def _original_location_from_mapping(
        cls,
        mapping: dict[str, Any],
        *,
        source_map: dict[str, Any],
        requested_generated_line_number: int,
        requested_generated_column_number: int,
        strategy: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> GeneratedLocation | None:
        sources = source_map.get("sources", []) if isinstance(source_map.get("sources"), list) else []
        source_index = mapping.get("source_index")
        if not isinstance(source_index, int) or not (0 <= source_index < len(sources)):
            return None
        raw_source = str(sources[source_index])
        resolved_source = cls._join_source_root(str(source_map.get("sourceRoot") or ""), raw_source)
        names = source_map.get("names", []) if isinstance(source_map.get("names"), list) else []
        metadata = {
            "source_index": source_index,
            "sources_count": len(sources),
            "names_count": len(names),
            "matched_source": raw_source,
            "resolved_source": resolved_source,
            "requested_generated_line_number": requested_generated_line_number,
            "requested_generated_column_number": requested_generated_column_number,
            "matched_generated_line_number": mapping.get("generated_line_number"),
            "matched_generated_column_number": mapping.get("generated_column_number"),
        }
        name_index = mapping.get("name_index")
        if isinstance(name_index, int):
            metadata["name_index"] = name_index
            if 0 <= name_index < len(names):
                metadata["name"] = str(names[name_index])
        if source_map.get("sourceRoot"):
            metadata["sourceRoot"] = source_map.get("sourceRoot")
        if extra_metadata:
            metadata.update(extra_metadata)
        return GeneratedLocation(
            line_number=int(mapping["generated_line_number"]),
            column_number=int(mapping["generated_column_number"]),
            source=resolved_source,
            original_line_number=int(mapping["original_line_number"]),
            original_column_number=int(mapping["original_column_number"]),
            strategy=strategy,
            metadata=metadata,
        )

    @staticmethod
    def _mapping_has_original_location(mapping: dict[str, Any]) -> bool:
        return (
            isinstance(mapping.get("source_index"), int)
            and isinstance(mapping.get("original_line_number"), int)
            and isinstance(mapping.get("original_column_number"), int)
        )

    @staticmethod
    def _section_offset_before_or_at(offset_line: int, offset_column: int, line_number: int, column_number: int) -> bool:
        return offset_line < line_number or (offset_line == line_number and offset_column <= column_number)

    @classmethod
    def _find_source_index(cls, sources: list[Any], *, original_source: str, source_root: str = "") -> tuple[int, str, dict[str, Any]]:
        candidates = cls._source_candidates(original_source)
        for index, source in enumerate(sources):
            raw_source = str(source)
            joined = cls._join_source_root(source_root, raw_source)
            raw_candidates = cls._source_candidates(raw_source)
            joined_candidates = cls._source_candidates(joined)
            for candidate in cls._ordered_source_candidates(candidates):
                if candidate in raw_candidates or candidate in joined_candidates:
                    return (
                        index,
                        joined if source_root else raw_source,
                        {
                            "requested_source": original_source,
                            "matched_source": raw_source,
                            "resolved_source": joined if source_root else raw_source,
                            "normalized_match": candidate,
                            "source_root_applied": bool(source_root),
                            "url_equivalence": cls._source_has_url_semantics(raw_source)
                            or cls._source_has_url_semantics(joined)
                            or cls._source_has_url_semantics(original_source),
                        },
                    )
        return -1, original_source, {"requested_source": original_source, "matched": False}

    @staticmethod
    def _source_candidates(source: str) -> set[str]:
        normalized = SourceMapRemapper._normalize_source(source)
        candidates = {normalized, normalized.lstrip("./").lstrip("/")}
        url_parts = urlsplit(source.replace("\\", "/").strip())
        if url_parts.scheme:
            normalized_url_path = SourceMapRemapper._normalize_path(url_parts.path)
            host_path = SourceMapRemapper._normalize_source(f"{url_parts.netloc}/{normalized_url_path}" if url_parts.netloc else normalized_url_path)
            candidates.add(host_path)
            candidates.add(normalized_url_path)
            candidates.add(normalized_url_path.lstrip("/"))
            if url_parts.scheme == "webpack" and url_parts.netloc:
                candidates.add(SourceMapRemapper._normalize_source(f"{url_parts.netloc}/{normalized_url_path}"))
        if "://" in normalized:
            candidates.add(normalized.split("://", 1)[1].lstrip("/"))
        return {item for item in candidates if item}

    @staticmethod
    def _ordered_source_candidates(candidates: set[str]) -> list[str]:
        return sorted(candidates, key=lambda item: ("://" not in item, -len(item), item))

    @staticmethod
    def _normalize_source(source: str) -> str:
        source = unquote(source.replace("\\", "/").strip())
        url_parts = urlsplit(source)
        if url_parts.scheme:
            normalized_path = SourceMapRemapper._normalize_path(url_parts.path)
            return urlunsplit((url_parts.scheme, url_parts.netloc, normalized_path, "", "")).lstrip("./")
        return SourceMapRemapper._normalize_path(source).lstrip("./")

    @staticmethod
    def _normalize_path(path: str) -> str:
        stripped = path.split("#", 1)[0].split("?", 1)[0]
        had_leading_slash = stripped.startswith("/")
        normalized = posixpath.normpath(stripped or "")
        if normalized == ".":
            normalized = ""
        if had_leading_slash and normalized and not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.lstrip("./")

    @staticmethod
    def _source_has_url_semantics(source: str) -> bool:
        value = source.replace("\\", "/").strip()
        parts = urlsplit(value)
        return bool(parts.scheme or "?" in value or "#" in value or "/./" in value or "/../" in value)

    @staticmethod
    def _join_source_root(source_root: str, source: str) -> str:
        if not source_root:
            return source
        if source.startswith(("http://", "https://", "webpack://", "file://")):
            return source
        if source_root.endswith("/") or source.startswith("/"):
            return f"{source_root}{source}"
        return f"{source_root}/{source}"

    @classmethod
    def iter_mappings(cls, source_map: dict[str, Any]) -> list[dict[str, Any]]:
        mappings = str(source_map.get("mappings") or "")
        results: list[dict[str, Any]] = []
        previous_source = 0
        previous_original_line = 0
        previous_original_column = 0
        previous_name = 0
        for generated_line, line in enumerate(mappings.split(";")):
            previous_generated_column = 0
            if not line:
                continue
            for segment in line.split(","):
                if not segment:
                    continue
                values = cls.decode_vlq_segment(segment)
                if not values:
                    continue
                previous_generated_column += values[0]
                item: dict[str, Any] = {
                    "generated_line_number": generated_line,
                    "generated_column_number": previous_generated_column,
                }
                if len(values) >= 4:
                    previous_source += values[1]
                    previous_original_line += values[2]
                    previous_original_column += values[3]
                    item.update(
                        {
                            "source_index": previous_source,
                            "original_line_number": previous_original_line,
                            "original_column_number": previous_original_column,
                        }
                    )
                    if len(values) >= 5:
                        previous_name += values[4]
                        item["name_index"] = previous_name
                results.append(item)
        return results

    @staticmethod
    def decode_vlq_segment(segment: str) -> list[int]:
        values: list[int] = []
        value = 0
        shift = 0
        for char in segment:
            digit = BASE64_VLQ_VALUES.get(char)
            if digit is None:
                raise ValueError(f"invalid base64 VLQ character: {char!r}")
            continuation = digit & 32
            digit_value = digit & 31
            value += digit_value << shift
            if continuation:
                shift += 5
                continue
            negative = value & 1
            decoded = value >> 1
            values.append(-decoded if negative else decoded)
            value = 0
            shift = 0
        if shift:
            raise ValueError("unterminated base64 VLQ segment")
        return values

    @staticmethod
    def _coerce_source_map(payload: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        return json.loads(payload)
