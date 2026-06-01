from __future__ import annotations

import hashlib
import json
import posixpath
import re
import urllib.request
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



SOURCE_MAPPING_URL_RE = re.compile(r"sourceMappingURL\s*=\s*([^\s*]+)")


def _redact_url(value: str) -> str:
    parts = urlsplit(value)
    if not parts.scheme:
        return value.split("?", 1)[0].split("#", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


@dataclass(slots=True)
class SourceMapFetchSpec:
    """Review-gated request for fetching external Source Map payloads.

    The default path is plan-only.  Network fetching is allowed only when the
    caller explicitly sets ``fetch_source_map`` and ``review_approved``.  The
    built-in fetcher uses Python's urllib without cookies or caller-provided
    authorization headers; browser credentials are never reused.
    """

    script_url: str
    source_map_url: str | None = None
    script_source: str | None = None
    fetch_source_map: bool = False
    review_approved: bool = False
    allow_cross_origin: bool = False
    allowed_hosts: tuple[str, ...] = ()
    fetch_indexed_section_urls: bool = False
    max_bytes: int = 2_000_000

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFetchSpec | None":
        context = context or {}
        script_url = context.get("script_url", context.get("scriptUrl", context.get("url")))
        script_source = context.get("script_source", context.get("scriptSource", context.get("bundle_source", context.get("bundleSource"))))
        source_map_url = context.get("source_map_url", context.get("sourceMapUrl", context.get("source_mapping_url", context.get("sourceMappingURL"))))
        if not script_url and not source_map_url:
            return None
        allowed_hosts = cls._coerce_hosts(context.get("source_map_allowed_hosts", context.get("sourceMapAllowedHosts", context.get("allowed_hosts", context.get("allowedHosts")))))
        return cls(
            script_url=str(script_url or ""),
            source_map_url=str(source_map_url).strip() if source_map_url else None,
            script_source=str(script_source) if script_source is not None else None,
            fetch_source_map=bool(context.get("fetch_source_map", context.get("fetchSourceMap", False))),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))),
            allow_cross_origin=bool(context.get("allow_cross_origin_source_map", context.get("allowCrossOriginSourceMap", False))),
            allowed_hosts=tuple(allowed_hosts),
            fetch_indexed_section_urls=bool(context.get("fetch_indexed_section_urls", context.get("fetchIndexedSectionUrls", False))),
            max_bytes=int(context.get("source_map_max_bytes", context.get("sourceMapMaxBytes", 2_000_000)) or 2_000_000),
        )

    @staticmethod
    def _coerce_hosts(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = value.split(",")
        elif isinstance(value, (list, tuple, set)):
            raw = [str(item) for item in value]
        else:
            raw = []
        return [item.strip().lower() for item in raw if item and item.strip()]


@dataclass(slots=True)
class SourceMapFetchResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "result": self.result,
            "side_effect_policy": self.side_effect_policy,
            "error": self.error,
            "reason": self.reason,
        }


class SourceMapFetchManager:
    """Plan and explicitly fetch external Source Maps with conservative policy gates."""

    def __init__(self, fetcher: Any | None = None) -> None:
        self.fetcher = fetcher or self._urllib_fetcher

    def plan_or_fetch(self, spec: SourceMapFetchSpec | None) -> SourceMapFetchResult:
        if spec is None:
            return SourceMapFetchResult(status="unsupported", reason="missing_source_map_fetch_request")
        plan = self._build_plan(spec)
        if not spec.fetch_source_map:
            return SourceMapFetchResult(
                status="planned",
                plan=plan,
                result={"attempted": False, "reason": "fetch_source_map_not_requested"},
                side_effect_policy=plan["side_effect_policy"],
            )
        if not spec.review_approved:
            return SourceMapFetchResult(
                status="blocked",
                plan=plan,
                result={"attempted": False, "reason": "review_approval_required"},
                side_effect_policy=plan["side_effect_policy"],
                reason="review_approval_required",
            )
        if not plan.get("fetch_allowed"):
            return SourceMapFetchResult(
                status="blocked",
                plan=plan,
                result={"attempted": False, "reason": plan.get("blocking_reason") or "source_map_url_not_allowed"},
                side_effect_policy=plan["side_effect_policy"],
                reason=str(plan.get("blocking_reason") or "source_map_url_not_allowed"),
            )
        try:
            payload_bytes = self.fetcher(plan["source_map_url"], spec.max_bytes)
            source_map = self._parse_source_map_bytes(payload_bytes)
            section_results = self._fetch_indexed_sections(source_map, plan["source_map_url"], spec) if spec.fetch_indexed_section_urls else []
            result = self._result_payload(
                source_map=source_map,
                source_map_url=plan["source_map_url"],
                payload_bytes=payload_bytes,
                section_results=section_results,
                spec=spec,
            )
            return SourceMapFetchResult(status="success", plan=plan, result=result, side_effect_policy=self._executed_policy(spec, section_results))
        except Exception as exc:
            return SourceMapFetchResult(
                status="failed",
                plan=plan,
                result={"attempted": True, "ok": False, "error": str(exc)},
                side_effect_policy=self._executed_policy(spec, []),
                error=str(exc),
            )

    @classmethod
    def _build_plan(cls, spec: SourceMapFetchSpec) -> dict[str, Any]:
        source_map_url = cls._resolve_source_map_url(spec)
        policy = cls._url_policy(source_map_url, spec.script_url, allowed_hosts=spec.allowed_hosts, allow_cross_origin=spec.allow_cross_origin)
        return {
            "schema_version": "reverse-deepagent.source-map-fetch-plan.v1",
            "status": "ready_for_review" if policy["allowed"] else "blocked",
            "script_url": spec.script_url,
            "script_url_redacted": _redact_url(spec.script_url),
            "source_map_url": source_map_url,
            "source_map_url_redacted": _redact_url(source_map_url) if source_map_url else "",
            "source_mapping_url_detected": bool(source_map_url),
            "fetch_allowed": bool(policy["allowed"]),
            "blocking_reason": policy.get("reason"),
            "url_policy": policy,
            "review_required": True,
            "fetch_indexed_section_urls": spec.fetch_indexed_section_urls,
            "max_bytes": spec.max_bytes,
            "approval_requirements": [
                "confirm_source_map_url_origin",
                "approve_credentialless_source_map_fetch",
                "review_payload_digest_and_size_before_remap",
            ],
            "side_effect_policy": {
                "plan_only_by_default": True,
                "requires_fetch_source_map": True,
                "requires_review_approval": True,
                "credentialless_fetch": True,
                "browser_cookies_sent": False,
                "authorization_headers_sent": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
            "next_action": "approve_fetch_source_map" if policy["allowed"] else "provide_same_origin_or_allowlisted_source_map_url",
        }

    @staticmethod
    def _resolve_source_map_url(spec: SourceMapFetchSpec) -> str:
        raw_url = spec.source_map_url or SourceMapFetchManager._extract_source_mapping_url(spec.script_source or "")
        if not raw_url:
            return ""
        return urljoin(spec.script_url, raw_url.strip()) if spec.script_url else raw_url.strip()

    @staticmethod
    def _extract_source_mapping_url(script_source: str) -> str:
        matches = SOURCE_MAPPING_URL_RE.findall(script_source or "")
        return matches[-1].strip() if matches else ""

    @staticmethod
    def _url_policy(url: str, script_url: str, *, allowed_hosts: tuple[str, ...], allow_cross_origin: bool) -> dict[str, Any]:
        if not url:
            return {"allowed": False, "reason": "source_map_url_missing"}
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return {"allowed": False, "reason": "unsupported_source_map_url_scheme", "scheme": parts.scheme}
        script_parts = urlsplit(script_url)
        same_origin = bool(script_parts.scheme and script_parts.netloc and parts.scheme == script_parts.scheme and parts.netloc.lower() == script_parts.netloc.lower())
        host_allowed = parts.netloc.lower() in allowed_hosts or parts.hostname and parts.hostname.lower() in allowed_hosts
        allowed = same_origin or allow_cross_origin or bool(host_allowed)
        return {
            "allowed": bool(allowed),
            "reason": None if allowed else "cross_origin_source_map_requires_allowlist_or_override",
            "same_origin": same_origin,
            "allow_cross_origin": allow_cross_origin,
            "host_allowed": bool(host_allowed),
            "source_map_host": parts.netloc.lower(),
            "script_host": script_parts.netloc.lower(),
        }

    def _fetch_indexed_sections(self, source_map: dict[str, Any], base_url: str, spec: SourceMapFetchSpec) -> list[dict[str, Any]]:
        sections = source_map.get("sections")
        if not isinstance(sections, list):
            return []
        results: list[dict[str, Any]] = []
        for index, section in enumerate(sections):
            if not isinstance(section, dict) or not section.get("url"):
                continue
            section_url = urljoin(base_url, str(section["url"]))
            policy = self._url_policy(section_url, base_url, allowed_hosts=spec.allowed_hosts, allow_cross_origin=spec.allow_cross_origin)
            entry: dict[str, Any] = {
                "section_index": index,
                "section_url": section_url,
                "section_url_redacted": _redact_url(section_url),
                "fetch_allowed": bool(policy["allowed"]),
                "url_policy": policy,
            }
            if not policy["allowed"]:
                entry.update({"status": "blocked", "reason": policy.get("reason")})
                results.append(entry)
                continue
            try:
                payload_bytes = self.fetcher(section_url, spec.max_bytes)
                section_map = self._parse_source_map_bytes(payload_bytes)
                entry.update(self._source_map_summary(section_map, payload_bytes))
                entry.update({"status": "success", "ok": True})
            except Exception as exc:
                entry.update({"status": "failed", "ok": False, "error": str(exc)})
            results.append(entry)
        return results

    @staticmethod
    def _parse_source_map_bytes(payload: bytes | str) -> dict[str, Any]:
        raw = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("source map payload is not a JSON object")
        return parsed

    @classmethod
    def _result_payload(cls, *, source_map: dict[str, Any], source_map_url: str, payload_bytes: bytes | str, section_results: list[dict[str, Any]], spec: SourceMapFetchSpec) -> dict[str, Any]:
        raw = payload_bytes.encode("utf-8") if isinstance(payload_bytes, str) else bytes(payload_bytes)
        summary = cls._source_map_summary(source_map, raw)
        return {
            "attempted": True,
            "ok": True,
            "status": "success",
            "source_map_url": source_map_url,
            "source_map_url_redacted": _redact_url(source_map_url),
            **summary,
            "indexed_section_fetch_attempted": bool(spec.fetch_indexed_section_urls),
            "indexed_section_results": section_results,
            "indexed_section_success_count": sum(1 for item in section_results if item.get("status") == "success"),
            "indexed_section_blocked_count": sum(1 for item in section_results if item.get("status") == "blocked"),
            "payload_exported": False,
        }

    @staticmethod
    def _source_map_summary(source_map: dict[str, Any], payload_bytes: bytes | str) -> dict[str, Any]:
        raw = payload_bytes.encode("utf-8") if isinstance(payload_bytes, str) else bytes(payload_bytes)
        sections = source_map.get("sections") if isinstance(source_map.get("sections"), list) else []
        sources = source_map.get("sources") if isinstance(source_map.get("sources"), list) else []
        return {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_count": len(raw),
            "version": source_map.get("version"),
            "sources_count": len(sources),
            "names_count": len(source_map.get("names") if isinstance(source_map.get("names"), list) else []),
            "section_count": len(sections),
            "indexed_section_url_count": sum(1 for item in sections if isinstance(item, dict) and item.get("url")),
        }

    @staticmethod
    def _executed_policy(spec: SourceMapFetchSpec, section_results: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "plan_only_by_default": False,
            "requires_fetch_source_map": True,
            "requires_review_approval": True,
            "credentialless_fetch": True,
            "browser_cookies_sent": False,
            "authorization_headers_sent": False,
            "indexed_section_url_fetch_requested": bool(spec.fetch_indexed_section_urls),
            "indexed_section_url_fetch_count": len(section_results),
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _urllib_fetcher(url: str, max_bytes: int) -> bytes:
        limit = max(1, int(max_bytes))
        request = urllib.request.Request(url, headers={"Accept": "application/json, application/source-map+json;q=0.9,*/*;q=0.1"})
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310 - reviewed source-map fetch path; URL policy is enforced before this call.
            payload = response.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("source map payload exceeds max_bytes")
        return payload

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
