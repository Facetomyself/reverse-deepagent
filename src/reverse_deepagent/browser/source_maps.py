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


@dataclass(slots=True)
class SourceMapLookupSpec:
    """Review-only Source Map consumer lookup request.

    The lookup consumes a caller-provided Source Map payload.  It can map
    original source positions to generated bundle positions, or generated
    bundle positions back to original source positions.  It never fetches
    Source Maps, starts a browser, sends CDP commands, installs logpoints, or
    calls MCP.
    """

    source_map: dict[str, Any] | None = None
    lookup_direction: str = "generated_to_original"
    original_source: str = ""
    original_line_number: int | None = None
    original_column_number: int = 0
    generated_line_number: int | None = None
    generated_column_number: int = 0
    source_map_bias: str = "greatest_lower_bound"

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapLookupSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_lookup",
                "sourceMapLookup",
                "source_map_consumer",
                "sourceMapConsumer",
                "source_map_generated_lookup",
                "sourceMapGeneratedLookup",
            )
        )
        source_map = cls._coerce_source_map(context.get("source_map", context.get("sourceMap")))
        if not requested and source_map is None:
            return None
        generated_line = context.get("generated_line", context.get("generatedLine", context.get("generated_line_number", context.get("generatedLineNumber"))))
        generated_column = context.get("generated_column", context.get("generatedColumn", context.get("generated_column_number", context.get("generatedColumnNumber", 0))))
        original_line = context.get("original_line", context.get("originalLine", context.get("original_line_number", context.get("originalLineNumber"))))
        original_column = context.get("original_column", context.get("originalColumn", context.get("original_column_number", context.get("originalColumnNumber", 0))))
        direction = str(context.get("lookup_direction", context.get("lookupDirection", "")) or "").strip().lower()
        if not direction:
            direction = "generated_to_original" if generated_line is not None else "original_to_generated"
        generated_line_base = int(context.get("generated_line_base", context.get("generatedLineBase", 0)) or 0)
        generated_column_base = int(context.get("generated_column_base", context.get("generatedColumnBase", 0)) or 0)
        original_line_base = int(context.get("original_line_base", context.get("originalLineBase", 0)) or 0)
        original_column_base = int(context.get("original_column_base", context.get("originalColumnBase", 0)) or 0)
        return cls(
            source_map=source_map,
            lookup_direction=direction.replace("-", "_"),
            original_source=str(context.get("original_source", context.get("originalSource", context.get("source", ""))) or ""),
            original_line_number=(int(original_line) - original_line_base) if original_line is not None else None,
            original_column_number=int(original_column or 0) - original_column_base,
            generated_line_number=(int(generated_line) - generated_line_base) if generated_line is not None else None,
            generated_column_number=int(generated_column or 0) - generated_column_base,
            source_map_bias=str(context.get("source_map_bias", context.get("sourceMapBias", "greatest_lower_bound")) or "greatest_lower_bound"),
        )

    @staticmethod
    def _coerce_source_map(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
        return None


@dataclass(slots=True)
class SourceMapLookupResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapLookupManager:
    """Build a review-only Source Map consumer lookup descriptor."""

    def lookup(self, spec: SourceMapLookupSpec | None) -> SourceMapLookupResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapLookupResult(status="unsupported", reason="missing_source_map_lookup_request", side_effect_policy=policy)
        if not isinstance(spec.source_map, dict):
            descriptor = self._base_descriptor(spec, status="blocked", reason="missing_source_map_payload")
            return SourceMapLookupResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_source_map_payload")
        try:
            descriptor = self._descriptor(spec)
            return SourceMapLookupResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(spec, status="failed", reason="source_map_lookup_failed")
            descriptor["error"] = str(exc)
            return SourceMapLookupResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="source_map_lookup_failed", error=str(exc))

    def _descriptor(self, spec: SourceMapLookupSpec) -> dict[str, Any]:
        assert spec.source_map is not None
        blockers = self._blockers(spec)
        location: GeneratedLocation | None = None
        if not blockers:
            if spec.lookup_direction in {"generated_to_original", "generated"}:
                location = SourceMapRemapper.location_from_generated(
                    spec.source_map,
                    generated_line_number=int(spec.generated_line_number or 0),
                    generated_column_number=spec.generated_column_number,
                    bias=spec.source_map_bias,
                )
            elif spec.lookup_direction in {"original_to_generated", "original"}:
                location = SourceMapRemapper.location_from_source_map(
                    spec.source_map,
                    original_source=spec.original_source,
                    original_line_number=int(spec.original_line_number or 0),
                    original_column_number=spec.original_column_number,
                    bias=spec.source_map_bias,
                )
            else:
                blockers.append("unsupported_lookup_direction")
        if location is None and not blockers:
            blockers.append("no_source_map_mapping_found")
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-lookup.v1",
            "status": status,
            "review_only": True,
            "lookup_request": self._lookup_request(spec),
            "source_map_summary": self._source_map_summary(spec.source_map),
            "location": location.to_dict() if location else {},
            "mapping_found": location is not None,
            "blockers": blockers,
            "next_action": "review_source_map_lookup_before_debugger_or_hook_use" if location else "provide_source_map_payload_and_lookup_position",
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, spec: SourceMapLookupSpec, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-lookup.v1",
            "status": status,
            "review_only": True,
            "reason": reason,
            "lookup_request": self._lookup_request(spec),
            "source_map_summary": self._source_map_summary(spec.source_map or {}),
            "location": {},
            "mapping_found": False,
            "blockers": [reason],
            "next_action": "provide_source_map_payload_and_lookup_position",
            "side_effect_policy": self._side_effect_policy(),
        }

    @staticmethod
    def _lookup_request(spec: SourceMapLookupSpec) -> dict[str, Any]:
        return {
            "lookup_direction": spec.lookup_direction,
            "original_source": spec.original_source,
            "original_line_number": spec.original_line_number,
            "original_column_number": spec.original_column_number,
            "generated_line_number": spec.generated_line_number,
            "generated_column_number": spec.generated_column_number,
            "source_map_bias": spec.source_map_bias,
        }

    @staticmethod
    def _source_map_summary(source_map: dict[str, Any]) -> dict[str, Any]:
        sources = source_map.get("sources") if isinstance(source_map.get("sources"), list) else []
        names = source_map.get("names") if isinstance(source_map.get("names"), list) else []
        sections = source_map.get("sections") if isinstance(source_map.get("sections"), list) else []
        sources_content = source_map.get("sourcesContent") if isinstance(source_map.get("sourcesContent"), list) else []
        return {
            "version": source_map.get("version"),
            "sources_count": len(sources),
            "names_count": len(names),
            "section_count": len(sections),
            "sources_content_count": len(sources_content),
            "sourceRoot": source_map.get("sourceRoot") or "",
            "indexed_section_depth": BundlerSymbolScopeManager._indexed_depth(source_map),
            "source_map_payload_present": bool(source_map),
        }

    @staticmethod
    def _blockers(spec: SourceMapLookupSpec) -> list[str]:
        blockers: list[str] = []
        if spec.lookup_direction in {"generated_to_original", "generated"}:
            if spec.generated_line_number is None:
                blockers.append("missing_generated_line_number")
        elif spec.lookup_direction in {"original_to_generated", "original"}:
            if not spec.original_source:
                blockers.append("missing_original_source")
            if spec.original_line_number is None:
                blockers.append("missing_original_line_number")
        else:
            blockers.append("unsupported_lookup_direction")
        return blockers

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapSourceContentSpec:
    """Review-only Source Map ``sourcesContent`` availability request."""

    source_map: dict[str, Any] | None = None
    original_source: str = ""
    source_index: int | None = None
    include_preview_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapSourceContentSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_source_content",
                "sourceMapSourceContent",
                "source_map_sources_content",
                "sourceMapSourcesContent",
                "review_source_map_source_content",
                "reviewSourceMapSourceContent",
            )
        )
        source_map = cls._coerce_source_map(context.get("source_map", context.get("sourceMap")))
        if not requested and source_map is None:
            return None
        raw_source_index = context.get("source_index", context.get("sourceIndex", context.get("source_map_source_index", context.get("sourceMapSourceIndex"))))
        return cls(
            source_map=source_map,
            original_source=str(context.get("original_source", context.get("originalSource", context.get("source", ""))) or ""),
            source_index=int(raw_source_index) if raw_source_index is not None else None,
            include_preview_requested=bool(context.get("include_source_preview", context.get("includeSourcePreview", False))),
        )

    @staticmethod
    def _coerce_source_map(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
        return None


@dataclass(slots=True)
class SourceMapSourceContentResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapSourceContentManager:
    """Build a secret-safe review descriptor for Source Map sourcesContent."""

    def review(self, spec: SourceMapSourceContentSpec | None) -> SourceMapSourceContentResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapSourceContentResult(status="unsupported", reason="missing_source_map_source_content_request", side_effect_policy=policy)
        if not isinstance(spec.source_map, dict):
            descriptor = self._base_descriptor(spec, status="blocked", reason="missing_source_map_payload")
            return SourceMapSourceContentResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_source_map_payload")
        try:
            descriptor = self._descriptor(spec)
            return SourceMapSourceContentResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(spec, status="failed", reason="source_map_source_content_review_failed")
            descriptor["error"] = str(exc)
            return SourceMapSourceContentResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="source_map_source_content_review_failed", error=str(exc))

    def _descriptor(self, spec: SourceMapSourceContentSpec) -> dict[str, Any]:
        assert spec.source_map is not None
        entries = self._source_entries(spec.source_map)
        entry = self._select_entry(entries, spec)
        blockers = self._blockers(spec, entry)
        content = entry.get("content") if entry else None
        content_available = isinstance(content, str)
        if entry and not content_available:
            blockers.append("source_content_missing")
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-source-content.v1",
            "status": status,
            "review_only": True,
            "source_request": self._source_request(spec),
            "source_map_summary": self._source_map_summary(spec.source_map, entries),
            "source_match": self._source_match_payload(entry, spec),
            "content_summary": self._content_summary(content if isinstance(content, str) else None, spec),
            "source_content_available": content_available,
            "blockers": blockers,
            "next_action": "review_source_content_availability_before_debugger_or_rebuild" if content_available else "provide_source_map_with_sources_content",
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, spec: SourceMapSourceContentSpec, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-source-content.v1",
            "status": status,
            "review_only": True,
            "reason": reason,
            "source_request": self._source_request(spec),
            "source_map_summary": self._source_map_summary(spec.source_map or {}, []),
            "source_match": {"matched": False, "reason": reason},
            "content_summary": self._content_summary(None, spec),
            "source_content_available": False,
            "blockers": [reason],
            "next_action": "provide_source_map_with_sources_content",
            "side_effect_policy": self._side_effect_policy(),
        }

    @staticmethod
    def _source_request(spec: SourceMapSourceContentSpec) -> dict[str, Any]:
        return {
            "original_source": spec.original_source,
            "source_index": spec.source_index,
            "include_preview_requested": spec.include_preview_requested,
            "raw_source_content_exported": False,
        }

    @classmethod
    def _source_map_summary(cls, source_map: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
        sources = source_map.get("sources") if isinstance(source_map.get("sources"), list) else []
        names = source_map.get("names") if isinstance(source_map.get("names"), list) else []
        sections = source_map.get("sections") if isinstance(source_map.get("sections"), list) else []
        available_count = sum(1 for entry in entries if isinstance(entry.get("content"), str))
        return {
            "version": source_map.get("version"),
            "sources_count": len(sources),
            "names_count": len(names),
            "section_count": len(sections),
            "flattened_source_count": len(entries),
            "sources_content_available_count": available_count,
            "sources_content_missing_count": max(0, len(entries) - available_count),
            "sourceRoot": source_map.get("sourceRoot") or "",
            "indexed_section_depth": BundlerSymbolScopeManager._indexed_depth(source_map),
            "source_map_payload_present": bool(source_map),
        }

    @staticmethod
    def _content_summary(content: str | None, spec: SourceMapSourceContentSpec) -> dict[str, Any]:
        if content is None:
            return {
                "available": False,
                "char_count": 0,
                "byte_count": 0,
                "line_count": 0,
                "sha256": "",
                "preview_requested": spec.include_preview_requested,
                "preview_exported": False,
                "raw_content_exported": False,
            }
        encoded = content.encode("utf-8")
        return {
            "available": True,
            "char_count": len(content),
            "byte_count": len(encoded),
            "line_count": content.count("\n") + 1 if content else 0,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "preview_requested": spec.include_preview_requested,
            "preview_exported": False,
            "raw_content_exported": False,
        }

    @classmethod
    def _source_match_payload(cls, entry: dict[str, Any] | None, spec: SourceMapSourceContentSpec) -> dict[str, Any]:
        if not entry:
            return {"matched": False, "requested_source": spec.original_source, "requested_source_index": spec.source_index}
        payload = {key: value for key, value in entry.items() if key != "content"}
        payload.update({"matched": True, "requested_source": spec.original_source, "requested_source_index": spec.source_index})
        return payload

    @classmethod
    def _blockers(cls, spec: SourceMapSourceContentSpec, entry: dict[str, Any] | None) -> list[str]:
        blockers: list[str] = []
        if spec.source_index is None and not spec.original_source:
            blockers.append("missing_source_selector")
        if (spec.source_index is not None or spec.original_source) and entry is None:
            blockers.append("source_not_found_in_source_map")
        return blockers

    @classmethod
    def _select_entry(cls, entries: list[dict[str, Any]], spec: SourceMapSourceContentSpec) -> dict[str, Any] | None:
        if spec.source_index is not None:
            for entry in entries:
                if entry.get("flattened_source_index") == spec.source_index:
                    return entry
        if spec.original_source:
            for entry in entries:
                if cls._source_matches(str(entry.get("source", "")), spec.original_source) or cls._source_matches(
                    str(entry.get("resolved_source", "")), spec.original_source
                ):
                    return entry
        return None

    @staticmethod
    def _source_matches(candidate: str, requested: str) -> bool:
        return bool(SourceMapRemapper._source_candidates(candidate).intersection(SourceMapRemapper._source_candidates(requested)))

    @classmethod
    def _source_entries(
        cls,
        source_map: dict[str, Any],
        *,
        section_stack: list[dict[str, Any]] | None = None,
        flattened_start: int = 0,
    ) -> list[dict[str, Any]]:
        section_stack = section_stack or []
        sections = source_map.get("sections")
        if isinstance(sections, list):
            collected: list[dict[str, Any]] = []
            next_index = flattened_start
            for section_index, section in enumerate(sections):
                if not isinstance(section, dict) or not isinstance(section.get("map"), dict):
                    continue
                offset = section.get("offset") if isinstance(section.get("offset"), dict) else {}
                section_entry = {
                    "section_index": section_index,
                    "offset_line": int(offset.get("line", 0) or 0),
                    "offset_column": int(offset.get("column", 0) or 0),
                }
                nested = cls._source_entries(section["map"], section_stack=[*section_stack, section_entry], flattened_start=next_index)
                collected.extend(nested)
                next_index += len(nested)
            return collected
        sources = source_map.get("sources") if isinstance(source_map.get("sources"), list) else []
        sources_content = source_map.get("sourcesContent") if isinstance(source_map.get("sourcesContent"), list) else []
        source_root = str(source_map.get("sourceRoot") or "")
        entries: list[dict[str, Any]] = []
        for index, source in enumerate(sources):
            content = sources_content[index] if index < len(sources_content) else None
            entries.append(
                {
                    "flattened_source_index": flattened_start + index,
                    "source_index": index,
                    "source": str(source),
                    "resolved_source": SourceMapRemapper._join_source_root(source_root, str(source)),
                    "sourceRoot": source_root,
                    "section_stack": list(section_stack),
                    "indexed_section_depth": len(section_stack),
                    "content": content if isinstance(content, str) else None,
                }
            )
        return entries

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapReadinessSpec:
    """Review-only Source Map evidence readiness join request.

    The readiness descriptor consumes already-produced Source Map review
    artifacts. It never parses raw source content, fetches Source Maps, starts
    a browser, sends CDP commands, installs logpoints, evaluates JavaScript, or
    calls MCP.
    """

    source_map_lookup: dict[str, Any] = field(default_factory=dict)
    source_map_source_content: dict[str, Any] = field(default_factory=dict)
    bundler_symbol_scope: dict[str, Any] = field(default_factory=dict)
    source_map_fetch_result: dict[str, Any] = field(default_factory=dict)
    source_map_fetch_plan: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapReadinessSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_readiness",
                "sourceMapReadiness",
                "review_source_map_readiness",
                "reviewSourceMapReadiness",
                "source_map_debugger_readiness",
                "sourceMapDebuggerReadiness",
            )
        )
        lookup = cls._object_alias(context, "source_map_lookup", "source-map-lookup", "sourceMapLookup", "source_map_consumer", "sourceMapConsumer")
        source_content = cls._object_alias(
            context,
            "source_map_source_content",
            "source-map-source-content",
            "sourceMapSourceContent",
            "source_map_sources_content",
            "sourceMapSourcesContent",
        )
        symbol_scope = cls._object_alias(
            context,
            "bundler_symbol_scope",
            "bundler-symbol-scope",
            "bundlerSymbolScope",
            "source_map_symbol_scope",
            "sourceMapSymbolScope",
        )
        fetch_result = cls._object_alias(context, "source_map_fetch_result", "source-map-fetch-result", "sourceMapFetchResult")
        fetch_plan = cls._object_alias(context, "source_map_fetch_plan", "source-map-fetch-plan", "sourceMapFetchPlan")
        if not requested and not any((lookup, source_content, symbol_scope, fetch_result, fetch_plan)):
            return None
        return cls(
            source_map_lookup=lookup,
            source_map_source_content=source_content,
            bundler_symbol_scope=symbol_scope,
            source_map_fetch_result=fetch_result,
            source_map_fetch_plan=fetch_plan,
        )

    @classmethod
    def _object_alias(cls, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {}


@dataclass(slots=True)
class SourceMapReadinessResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapReadinessManager:
    """Build a review-only join descriptor for Source Map debugger / rebuild readiness."""

    def review(self, spec: SourceMapReadinessSpec | None) -> SourceMapReadinessResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapReadinessResult(status="unsupported", reason="missing_source_map_readiness_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapReadinessResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_readiness_review_failed")
            descriptor["error"] = str(exc)
            return SourceMapReadinessResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="source_map_readiness_review_failed", error=str(exc))

    def _descriptor(self, spec: SourceMapReadinessSpec) -> dict[str, Any]:
        evidence_status = self._evidence_status(spec)
        readiness = self._readiness(evidence_status, spec)
        blockers = self._blockers(evidence_status, readiness)
        warnings = self._warnings(evidence_status, readiness)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-readiness.v1",
            "status": status,
            "review_only": True,
            "evidence_status": evidence_status,
            "readiness": readiness,
            "blockers": blockers,
            "warnings": warnings,
            "next_action": self._next_action(blockers, warnings, readiness),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-readiness.v1",
            "status": status,
            "review_only": True,
            "reason": reason,
            "evidence_status": {},
            "readiness": {},
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_lookup_and_source_content_descriptors",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _evidence_status(cls, spec: SourceMapReadinessSpec) -> dict[str, Any]:
        lookup = spec.source_map_lookup
        source_content = spec.source_map_source_content
        symbol_scope = spec.bundler_symbol_scope
        fetch_result = spec.source_map_fetch_result
        fetch_plan = spec.source_map_fetch_plan
        content_summary = source_content.get("content_summary") if isinstance(source_content.get("content_summary"), dict) else {}
        return {
            "lookup": {
                "present": bool(lookup),
                "status": cls._status(lookup),
                "mapping_found": bool(lookup.get("mapping_found", False)),
                "strategy": cls._nested_get(lookup, "location", "strategy") or "",
                "next_action": lookup.get("next_action") or "",
            },
            "source_content": {
                "present": bool(source_content),
                "status": cls._status(source_content),
                "source_content_available": bool(source_content.get("source_content_available", False)),
                "sha256": content_summary.get("sha256", ""),
                "raw_content_exported": bool(content_summary.get("raw_content_exported", source_content.get("raw_content_exported", False))),
                "preview_exported": bool(content_summary.get("preview_exported", source_content.get("preview_exported", False))),
                "next_action": source_content.get("next_action") or "",
            },
            "symbol_scope": {
                "present": bool(symbol_scope),
                "status": cls._status(symbol_scope),
                "scope_candidate_count": cls._intish(symbol_scope.get("scope_candidate_count")),
                "source_logpoint_reviewable": bool(cls._nested_get(symbol_scope, "hook_readiness", "source_logpoint_reviewable")),
                "bundler_kind": cls._nested_get(symbol_scope, "bundler_classification", "bundler_kind") or "unknown",
                "next_action": symbol_scope.get("next_action") or "",
            },
            "fetch_result": {
                "present": bool(fetch_result),
                "status": cls._status(fetch_result),
                "ok": bool(fetch_result.get("ok", False)),
                "attempted": bool(fetch_result.get("attempted", False)),
                "payload_exported": bool(fetch_result.get("payload_exported", False)),
            },
            "fetch_plan": {
                "present": bool(fetch_plan),
                "status": cls._status(fetch_plan),
                "fetch_allowed": bool(fetch_plan.get("fetch_allowed", False)),
                "source_map_url_redacted": fetch_plan.get("source_map_url_redacted", ""),
            },
        }

    @staticmethod
    def _readiness(evidence_status: dict[str, Any], spec: SourceMapReadinessSpec) -> dict[str, Any]:
        lookup = evidence_status["lookup"]
        source_content = evidence_status["source_content"]
        symbol_scope = evidence_status["symbol_scope"]
        fetch_result = evidence_status["fetch_result"]
        mapping_ready = bool(lookup["present"] and lookup["status"] == "ready_for_review" and lookup["mapping_found"])
        content_ready = bool(
            source_content["present"]
            and source_content["status"] == "ready_for_review"
            and source_content["source_content_available"]
            and not source_content["raw_content_exported"]
            and not source_content["preview_exported"]
        )
        symbol_reviewable = bool(symbol_scope["present"] and symbol_scope["status"] == "ready_for_review" and symbol_scope["source_logpoint_reviewable"])
        fetch_metadata_ready = bool(fetch_result["present"] and fetch_result["status"] in {"success", "ready_for_review", "planned"} and not fetch_result["payload_exported"])
        return {
            "debugger_location_ready": mapping_ready,
            "source_content_metadata_ready": content_ready,
            "source_logpoint_planning_ready": bool(mapping_ready and (symbol_reviewable or not spec.bundler_symbol_scope)),
            "rebuild_source_metadata_ready": bool(mapping_ready and content_ready),
            "bundler_scope_review_ready": symbol_reviewable,
            "fetch_metadata_ready": fetch_metadata_ready,
            "raw_source_content_exported": bool(source_content["raw_content_exported"]),
            "preview_exported": bool(source_content["preview_exported"]),
            "automatic_logpoint_install_supported": False,
            "automatic_debugger_execution_supported": False,
            "raw_source_aware_rebuild_supported": False,
        }

    @staticmethod
    def _blockers(evidence_status: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        lookup = evidence_status["lookup"]
        source_content = evidence_status["source_content"]
        if not lookup["present"]:
            blockers.append("source_map_lookup_descriptor_missing")
        elif lookup["status"] in {"blocked", "failed", "failure", "error", "unsupported"} or not lookup["mapping_found"]:
            blockers.append("source_map_lookup_not_ready")
        if not source_content["present"]:
            blockers.append("source_map_source_content_descriptor_missing")
        elif source_content["status"] in {"blocked", "failed", "failure", "error", "unsupported"} or not source_content["source_content_available"]:
            blockers.append("source_map_source_content_not_ready")
        if readiness.get("raw_source_content_exported"):
            blockers.append("raw_source_content_export_detected")
        if readiness.get("preview_exported"):
            blockers.append("source_content_preview_export_detected")
        return blockers

    @staticmethod
    def _warnings(evidence_status: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        symbol_scope = evidence_status["symbol_scope"]
        fetch_result = evidence_status["fetch_result"]
        if not symbol_scope["present"]:
            warnings.append("bundler_symbol_scope_descriptor_missing")
        elif symbol_scope["status"] in {"blocked", "failed", "failure", "error", "unsupported"}:
            warnings.append("bundler_symbol_scope_not_ready")
        elif not readiness.get("bundler_scope_review_ready"):
            warnings.append("bundler_symbol_scope_not_reviewable")
        if fetch_result["present"] and fetch_result["payload_exported"]:
            warnings.append("source_map_fetch_payload_exported")
        if not readiness.get("fetch_metadata_ready"):
            warnings.append("source_map_fetch_metadata_not_confirmed")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], warnings: list[str], readiness: dict[str, Any]) -> str:
        if "source_map_lookup_descriptor_missing" in blockers or "source_map_lookup_not_ready" in blockers:
            return "provide_ready_source_map_lookup_descriptor"
        if "source_map_source_content_descriptor_missing" in blockers or "source_map_source_content_not_ready" in blockers:
            return "provide_ready_source_map_source_content_descriptor"
        if "raw_source_content_export_detected" in blockers or "source_content_preview_export_detected" in blockers:
            return "replace_source_content_descriptor_with_metadata_only_version"
        if "bundler_symbol_scope_descriptor_missing" in warnings or "bundler_symbol_scope_not_ready" in warnings or "bundler_symbol_scope_not_reviewable" in warnings:
            return "review_source_map_readiness_then_add_bundler_symbol_scope"
        if readiness.get("rebuild_source_metadata_ready"):
            return "review_source_map_readiness_before_debugger_rebuild_or_logpoint_planning"
        return "review_source_map_readiness"

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _intish(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapConsumerActionPlanSpec:
    """Review-only action plan request for safe Source Map consumers.

    The action plan consumes existing Source Map readiness / lookup /
    sourcesContent metadata / bundler symbol-scope descriptors. It does not
    fetch Source Maps, export raw source content, install logpoints, execute
    debugger commands, run rebuilds, evaluate JavaScript, start browsers, or
    call MCP.
    """

    source_map_readiness: dict[str, Any] = field(default_factory=dict)
    source_map_lookup: dict[str, Any] = field(default_factory=dict)
    source_map_source_content: dict[str, Any] = field(default_factory=dict)
    bundler_symbol_scope: dict[str, Any] = field(default_factory=dict)
    requested_consumers: tuple[str, ...] = ("debugger", "source-logpoint", "rebuild", "hook")

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapConsumerActionPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_consumer_action_plan",
                "sourceMapConsumerActionPlan",
                "source_map_action_plan",
                "sourceMapActionPlan",
                "source_map_followup_plan",
                "sourceMapFollowupPlan",
            )
        )
        readiness = cls._object_alias(
            context,
            "source_map_readiness",
            "source-map-readiness",
            "sourceMapReadiness",
            "source_map_debugger_readiness",
            "sourceMapDebuggerReadiness",
        )
        lookup = cls._object_alias(context, "source_map_lookup", "source-map-lookup", "sourceMapLookup", "source_map_consumer", "sourceMapConsumer")
        source_content = cls._object_alias(
            context,
            "source_map_source_content",
            "source-map-source-content",
            "sourceMapSourceContent",
            "source_map_sources_content",
            "sourceMapSourcesContent",
        )
        symbol_scope = cls._object_alias(
            context,
            "bundler_symbol_scope",
            "bundler-symbol-scope",
            "bundlerSymbolScope",
            "source_map_symbol_scope",
            "sourceMapSymbolScope",
        )
        consumers = cls._coerce_consumers(
            context.get(
                "source_map_consumers",
                context.get("sourceMapConsumers", context.get("requested_consumers", context.get("requestedConsumers"))),
            )
        )
        if not requested and not any((readiness, lookup, source_content, symbol_scope)):
            return None
        return cls(
            source_map_readiness=readiness,
            source_map_lookup=lookup,
            source_map_source_content=source_content,
            bundler_symbol_scope=symbol_scope,
            requested_consumers=consumers,
        )

    @classmethod
    def _object_alias(cls, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {}

    @staticmethod
    def _coerce_consumers(payload: Any) -> tuple[str, ...]:
        if payload is None:
            return ("debugger", "source-logpoint", "rebuild", "hook")
        if isinstance(payload, str):
            raw_items = [item.strip() for item in payload.replace(";", ",").split(",")]
        elif isinstance(payload, (list, tuple, set)):
            raw_items = [str(item).strip() for item in payload]
        else:
            raw_items = []
        normalized: list[str] = []
        aliases = {
            "source_logpoint": "source-logpoint",
            "source-logpoints": "source-logpoint",
            "logpoint": "source-logpoint",
            "logpoints": "source-logpoint",
            "debugger-location": "debugger",
            "debugger_location": "debugger",
            "rebuild-source": "rebuild",
            "rebuild_source": "rebuild",
            "symbol-scope": "hook",
            "symbol_scope": "hook",
        }
        for item in raw_items:
            key = item.lower().replace(" ", "-")
            key = aliases.get(key, key)
            if key in {"debugger", "source-logpoint", "rebuild", "hook"} and key not in normalized:
                normalized.append(key)
        return tuple(normalized or ("debugger", "source-logpoint", "rebuild", "hook"))


@dataclass(slots=True)
class SourceMapConsumerActionPlanResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapConsumerActionPlanManager:
    """Build a review-only plan for debugger / hook / rebuild Source Map consumers."""

    def review(self, spec: SourceMapConsumerActionPlanSpec | None) -> SourceMapConsumerActionPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapConsumerActionPlanResult(status="unsupported", reason="missing_source_map_consumer_action_plan_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapConsumerActionPlanResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_consumer_action_plan_failed")
            descriptor["error"] = str(exc)
            return SourceMapConsumerActionPlanResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_consumer_action_plan_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapConsumerActionPlanSpec) -> dict[str, Any]:
        evidence_status = self._evidence_status(spec)
        action_plans = self._action_plans(spec, evidence_status)
        blockers = self._blockers(evidence_status, action_plans)
        warnings = self._warnings(evidence_status, action_plans)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-consumer-action-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "requested_consumers": list(spec.requested_consumers),
            "evidence_status": evidence_status,
            "action_plans": action_plans,
            "action_plan_count": len(action_plans),
            "blockers": blockers,
            "warnings": warnings,
            "next_action": self._next_action(blockers, warnings, action_plans),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-consumer-action-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "reason": reason,
            "requested_consumers": [],
            "evidence_status": {},
            "action_plans": [],
            "action_plan_count": 0,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_readiness_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _evidence_status(cls, spec: SourceMapConsumerActionPlanSpec) -> dict[str, Any]:
        readiness = spec.source_map_readiness
        readiness_fields = readiness.get("readiness") if isinstance(readiness.get("readiness"), dict) else {}
        evidence_status = readiness.get("evidence_status") if isinstance(readiness.get("evidence_status"), dict) else {}
        lookup = spec.source_map_lookup or (evidence_status.get("lookup") if isinstance(evidence_status.get("lookup"), dict) else {})
        source_content = spec.source_map_source_content or (evidence_status.get("source_content") if isinstance(evidence_status.get("source_content"), dict) else {})
        symbol_scope = spec.bundler_symbol_scope or (evidence_status.get("symbol_scope") if isinstance(evidence_status.get("symbol_scope"), dict) else {})
        return {
            "readiness": {
                "present": bool(readiness),
                "status": cls._status(readiness),
                "debugger_location_ready": bool(readiness_fields.get("debugger_location_ready", False)),
                "source_content_metadata_ready": bool(readiness_fields.get("source_content_metadata_ready", False)),
                "source_logpoint_planning_ready": bool(readiness_fields.get("source_logpoint_planning_ready", False)),
                "rebuild_source_metadata_ready": bool(readiness_fields.get("rebuild_source_metadata_ready", False)),
                "bundler_scope_review_ready": bool(readiness_fields.get("bundler_scope_review_ready", False)),
                "raw_source_content_exported": bool(readiness_fields.get("raw_source_content_exported", False)),
                "preview_exported": bool(readiness_fields.get("preview_exported", False)),
                "automatic_logpoint_install_supported": bool(readiness_fields.get("automatic_logpoint_install_supported", False)),
                "automatic_debugger_execution_supported": bool(readiness_fields.get("automatic_debugger_execution_supported", False)),
                "raw_source_aware_rebuild_supported": bool(readiness_fields.get("raw_source_aware_rebuild_supported", False)),
                "blockers": cls._string_list(readiness.get("blockers")),
                "warnings": cls._string_list(readiness.get("warnings")),
                "next_action": readiness.get("next_action") or "",
            },
            "lookup": {
                "present": bool(lookup),
                "status": cls._status(lookup),
                "mapping_found": bool(lookup.get("mapping_found", False)),
                "strategy": cls._nested_get(lookup, "location", "strategy") or lookup.get("strategy") or "",
                "source": cls._nested_get(lookup, "location", "source") or lookup.get("source") or "",
                "line_number": cls._nested_get(lookup, "location", "line_number"),
                "column_number": cls._nested_get(lookup, "location", "column_number"),
            },
            "source_content": {
                "present": bool(source_content),
                "status": cls._status(source_content),
                "source_content_available": bool(source_content.get("source_content_available", False)),
                "sha256": cls._nested_get(source_content, "content_summary", "sha256") or source_content.get("sha256") or "",
                "raw_content_exported": bool(cls._nested_get(source_content, "content_summary", "raw_content_exported") or source_content.get("raw_content_exported", False)),
                "preview_exported": bool(cls._nested_get(source_content, "content_summary", "preview_exported") or source_content.get("preview_exported", False)),
            },
            "symbol_scope": {
                "present": bool(symbol_scope),
                "status": cls._status(symbol_scope),
                "scope_candidate_count": cls._intish(symbol_scope.get("scope_candidate_count")),
                "source_logpoint_reviewable": bool(cls._nested_get(symbol_scope, "hook_readiness", "source_logpoint_reviewable") or symbol_scope.get("source_logpoint_reviewable", False)),
                "bundler_kind": cls._nested_get(symbol_scope, "bundler_classification", "bundler_kind") or symbol_scope.get("bundler_kind") or "unknown",
            },
        }

    @classmethod
    def _action_plans(cls, spec: SourceMapConsumerActionPlanSpec, evidence_status: dict[str, Any]) -> list[dict[str, Any]]:
        readiness = evidence_status["readiness"]
        lookup = evidence_status["lookup"]
        source_content = evidence_status["source_content"]
        symbol_scope = evidence_status["symbol_scope"]
        requested = set(spec.requested_consumers)
        plans: list[dict[str, Any]] = []
        if "debugger" in requested and readiness["debugger_location_ready"]:
            plans.append(
                cls._plan(
                    action_id="review-debugger-location-use",
                    consumer="debugger",
                    description="Review generated Source Map location metadata before any debugger location use.",
                    readiness_key="debugger_location_ready",
                    required_inputs=["source-map-readiness", "source-map-lookup"],
                    evidence={"mapping_strategy": lookup["strategy"], "source": lookup["source"], "line_number": lookup["line_number"], "column_number": lookup["column_number"]},
                    next_action="review_generated_to_original_location_before_debugger_use",
                )
            )
        if "source-logpoint" in requested and readiness["source_logpoint_planning_ready"]:
            plans.append(
                cls._plan(
                    action_id="review-source-logpoint-plan",
                    consumer="source-logpoint",
                    description="Plan a future source-level logpoint from reviewed Source Map readiness without installing it.",
                    readiness_key="source_logpoint_planning_ready",
                    required_inputs=["source-map-readiness", "source-map-lookup", "bundler-symbol-scope"],
                    evidence={"bundler_kind": symbol_scope["bundler_kind"], "scope_candidate_count": symbol_scope["scope_candidate_count"]},
                    next_action="review_source_logpoint_plan_before_installation",
                )
            )
        if "rebuild" in requested and readiness["rebuild_source_metadata_ready"]:
            plans.append(
                cls._plan(
                    action_id="review-rebuild-source-metadata-use",
                    consumer="rebuild",
                    description="Review metadata-only sourcesContent digest evidence before rebuild source metadata use.",
                    readiness_key="rebuild_source_metadata_ready",
                    required_inputs=["source-map-readiness", "source-map-source-content"],
                    evidence={"sha256": source_content["sha256"], "source_content_available": source_content["source_content_available"]},
                    next_action="review_source_content_digest_before_rebuild_metadata_use",
                )
            )
        if "hook" in requested and readiness["bundler_scope_review_ready"]:
            plans.append(
                cls._plan(
                    action_id="review-bundler-symbol-hook-candidate",
                    consumer="hook",
                    description="Review bundler symbol-scope candidates before any runtime hook planning.",
                    readiness_key="bundler_scope_review_ready",
                    required_inputs=["source-map-readiness", "bundler-symbol-scope"],
                    evidence={"bundler_kind": symbol_scope["bundler_kind"], "scope_candidate_count": symbol_scope["scope_candidate_count"]},
                    next_action="review_symbol_scope_before_runtime_hook_planning",
                )
            )
        return plans

    @staticmethod
    def _plan(*, action_id: str, consumer: str, description: str, readiness_key: str, required_inputs: list[str], evidence: dict[str, Any], next_action: str) -> dict[str, Any]:
        return {
            "action_id": action_id,
            "consumer": consumer,
            "description": description,
            "readiness_key": readiness_key,
            "status": "ready_for_review",
            "review_required": True,
            "plan_only": True,
            "execute_automatically": False,
            "required_inputs": required_inputs,
            "evidence": evidence,
            "next_action": next_action,
        }

    @staticmethod
    def _blockers(evidence_status: dict[str, Any], action_plans: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        readiness = evidence_status["readiness"]
        source_content = evidence_status["source_content"]
        if not readiness["present"]:
            blockers.append("source_map_readiness_descriptor_missing")
        elif readiness["status"] in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_readiness_not_ready")
        blockers.extend(f"source_map_readiness:{item}" for item in readiness["blockers"])
        if readiness["raw_source_content_exported"] or source_content["raw_content_exported"]:
            blockers.append("raw_source_content_export_detected")
        if readiness["preview_exported"] or source_content["preview_exported"]:
            blockers.append("source_content_preview_export_detected")
        if not action_plans:
            blockers.append("no_source_map_consumer_action_ready")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _warnings(evidence_status: dict[str, Any], action_plans: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        readiness = evidence_status["readiness"]
        lookup = evidence_status["lookup"]
        source_content = evidence_status["source_content"]
        symbol_scope = evidence_status["symbol_scope"]
        warnings.extend(f"source_map_readiness:{item}" for item in readiness["warnings"])
        if not lookup["present"]:
            warnings.append("source_map_lookup_descriptor_not_attached")
        if not source_content["present"]:
            warnings.append("source_map_source_content_descriptor_not_attached")
        if not symbol_scope["present"]:
            warnings.append("bundler_symbol_scope_descriptor_not_attached")
        if readiness["automatic_logpoint_install_supported"]:
            warnings.append("readiness_claims_automatic_logpoint_install_supported_ignored")
        if readiness["automatic_debugger_execution_supported"]:
            warnings.append("readiness_claims_automatic_debugger_execution_supported_ignored")
        if readiness["raw_source_aware_rebuild_supported"]:
            warnings.append("readiness_claims_raw_source_aware_rebuild_supported_ignored")
        if action_plans:
            warnings.append("consumer_actions_require_explicit_review")
        return list(dict.fromkeys(warnings))

    @staticmethod
    def _next_action(blockers: list[str], warnings: list[str], action_plans: list[dict[str, Any]]) -> str:
        if "source_map_readiness_descriptor_missing" in blockers:
            return "provide_ready_source_map_readiness_descriptor"
        if "source_map_readiness_not_ready" in blockers:
            return "resolve_source_map_readiness_blockers_before_consumer_planning"
        if "raw_source_content_export_detected" in blockers or "source_content_preview_export_detected" in blockers:
            return "replace_source_content_descriptor_with_metadata_only_version"
        if "no_source_map_consumer_action_ready" in blockers:
            return "provide_source_map_readiness_with_consumer_ready_fields"
        return "review_source_map_consumer_action_plan_before_debugger_rebuild_or_logpoint_execution"

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _string_list(payload: Any) -> list[str]:
        if not isinstance(payload, list):
            return []
        return [str(item) for item in payload if str(item).strip()]

    @staticmethod
    def _intish(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapConsumerMaterializationSpec:
    """Review-only materialization request for Source Map consumer action plans.

    This descriptor consumes a previously reviewed Source Map consumer action
    plan and turns selected action-plan entries into typed review payloads for
    debugger, source-logpoint, rebuild, and hook consumers. It still does not
    execute debugger commands, install logpoints or hooks, run rebuilds, fetch
    Source Maps, export raw source content, start browsers, evaluate JavaScript,
    call MCP, or touch mobile runtime chains.
    """

    source_map_consumer_action_plan: dict[str, Any] = field(default_factory=dict)
    source_map_readiness: dict[str, Any] = field(default_factory=dict)
    source_map_lookup: dict[str, Any] = field(default_factory=dict)
    source_map_source_content: dict[str, Any] = field(default_factory=dict)
    bundler_symbol_scope: dict[str, Any] = field(default_factory=dict)
    requested_action_ids: tuple[str, ...] = ()
    requested_consumers: tuple[str, ...] = ()

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapConsumerMaterializationSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_consumer_materialization",
                "sourceMapConsumerMaterialization",
                "source_map_materialization",
                "sourceMapMaterialization",
                "source_map_action_materialization",
                "sourceMapActionMaterialization",
            )
        )
        action_plan = cls._object_alias(
            context,
            "source_map_consumer_action_plan",
            "source-map-consumer-action-plan",
            "sourceMapConsumerActionPlan",
            "source_map_action_plan",
            "sourceMapActionPlan",
        )
        readiness = cls._object_alias(context, "source_map_readiness", "source-map-readiness", "sourceMapReadiness")
        lookup = cls._object_alias(context, "source_map_lookup", "source-map-lookup", "sourceMapLookup")
        source_content = cls._object_alias(
            context,
            "source_map_source_content",
            "source-map-source-content",
            "sourceMapSourceContent",
            "source_map_sources_content",
            "sourceMapSourcesContent",
        )
        symbol_scope = cls._object_alias(context, "bundler_symbol_scope", "bundler-symbol-scope", "bundlerSymbolScope")
        action_ids = cls._coerce_string_tuple(
            context.get(
                "source_map_materialization_action_ids",
                context.get("sourceMapMaterializationActionIds", context.get("requested_action_ids", context.get("requestedActionIds"))),
            )
        )
        consumers = cls._coerce_consumers(
            context.get(
                "source_map_materialization_consumers",
                context.get("sourceMapMaterializationConsumers", context.get("source_map_consumers", context.get("sourceMapConsumers"))),
            )
        )
        if not requested and not action_plan:
            return None
        return cls(
            source_map_consumer_action_plan=action_plan,
            source_map_readiness=readiness,
            source_map_lookup=lookup,
            source_map_source_content=source_content,
            bundler_symbol_scope=symbol_scope,
            requested_action_ids=action_ids,
            requested_consumers=consumers,
        )

    @classmethod
    def _object_alias(cls, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {}

    @staticmethod
    def _coerce_string_tuple(payload: Any) -> tuple[str, ...]:
        if payload is None:
            return ()
        if isinstance(payload, str):
            raw_items = [item.strip() for item in payload.replace(";", ",").split(",")]
        elif isinstance(payload, (list, tuple, set)):
            raw_items = [str(item).strip() for item in payload]
        else:
            raw_items = []
        normalized: list[str] = []
        for item in raw_items:
            if item and item not in normalized:
                normalized.append(item)
        return tuple(normalized)

    @staticmethod
    def _coerce_consumers(payload: Any) -> tuple[str, ...]:
        if payload is None:
            return ()
        if isinstance(payload, str):
            raw_items = [item.strip() for item in payload.replace(";", ",").split(",")]
        elif isinstance(payload, (list, tuple, set)):
            raw_items = [str(item).strip() for item in payload]
        else:
            raw_items = []
        aliases = {
            "source_logpoint": "source-logpoint",
            "source-logpoints": "source-logpoint",
            "logpoint": "source-logpoint",
            "logpoints": "source-logpoint",
            "debugger-location": "debugger",
            "debugger_location": "debugger",
            "rebuild-source": "rebuild",
            "rebuild_source": "rebuild",
            "symbol-scope": "hook",
            "symbol_scope": "hook",
        }
        normalized: list[str] = []
        for item in raw_items:
            key = aliases.get(item.lower().replace(" ", "-"), item.lower().replace(" ", "-"))
            if key in {"debugger", "source-logpoint", "rebuild", "hook"} and key not in normalized:
                normalized.append(key)
        return tuple(normalized)


@dataclass(slots=True)
class SourceMapConsumerMaterializationResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapConsumerMaterializationManager:
    """Materialize Source Map consumer action plans into typed review payloads."""

    def review(self, spec: SourceMapConsumerMaterializationSpec | None) -> SourceMapConsumerMaterializationResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapConsumerMaterializationResult(status="unsupported", reason="missing_source_map_consumer_materialization_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapConsumerMaterializationResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_consumer_materialization_failed")
            descriptor["error"] = str(exc)
            return SourceMapConsumerMaterializationResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_consumer_materialization_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapConsumerMaterializationSpec) -> dict[str, Any]:
        action_plan = spec.source_map_consumer_action_plan
        action_plans = self._action_plans(action_plan)
        blockers = self._input_blockers(spec, action_plan, action_plans)
        selected, selection_blockers = self._select_action_plans(spec, action_plans)
        blockers.extend(selection_blockers)
        materializations = [] if blockers else [self._materialize(plan, spec) for plan in selected]
        materialization_blockers = self._materialization_blockers(materializations)
        blockers.extend(materialization_blockers)
        warnings = self._warnings(spec, action_plan, selected, materializations)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-consumer-materialization.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "typed_payload_schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "requested_action_ids": list(spec.requested_action_ids),
            "requested_consumers": list(spec.requested_consumers),
            "source_action_plan_status": self._status(action_plan),
            "source_action_plan_count": len(action_plans),
            "selected_action_ids": [str(plan.get("action_id")) for plan in selected],
            "selected_consumer_count": len({str(item.get("consumer")) for item in selected if item.get("consumer")}),
            "materializations": materializations,
            "materialization_count": len(materializations),
            "typed_review_payloads": [item["typed_review_payload"] for item in materializations if isinstance(item.get("typed_review_payload"), dict)],
            "typed_review_payload_count": sum(1 for item in materializations if isinstance(item.get("typed_review_payload"), dict)),
            "typed_review_payload_consumers": [
                str(item.get("consumer"))
                for item in materializations
                if isinstance(item.get("typed_review_payload"), dict) and item.get("consumer")
            ],
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, materializations),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-consumer-materialization.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "reason": reason,
            "requested_action_ids": [],
            "requested_consumers": [],
            "source_action_plan_status": "",
            "source_action_plan_count": 0,
            "selected_action_ids": [],
            "selected_consumer_count": 0,
            "materializations": [],
            "materialization_count": 0,
            "typed_payload_schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "typed_review_payloads": [],
            "typed_review_payload_count": 0,
            "typed_review_payload_consumers": [],
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_consumer_action_plan_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, spec: SourceMapConsumerMaterializationSpec, action_plan: dict[str, Any], action_plans: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        if not action_plan:
            blockers.append("source_map_consumer_action_plan_missing")
        elif cls._status(action_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_consumer_action_plan_not_ready")
        blockers.extend(f"source_map_consumer_action_plan:{item}" for item in cls._string_list(action_plan.get("blockers")))
        policy = action_plan.get("side_effect_policy") if isinstance(action_plan.get("side_effect_policy"), dict) else {}
        evidence_status = action_plan.get("evidence_status") if isinstance(action_plan.get("evidence_status"), dict) else {}
        readiness = evidence_status.get("readiness") if isinstance(evidence_status.get("readiness"), dict) else {}
        source_content = evidence_status.get("source_content") if isinstance(evidence_status.get("source_content"), dict) else {}
        attached_source_content = spec.source_map_source_content
        if bool(policy.get("raw_source_content_exported")) or bool(readiness.get("raw_source_content_exported")) or bool(source_content.get("raw_content_exported")):
            blockers.append("raw_source_content_export_detected")
        if bool(policy.get("preview_exported")) or bool(readiness.get("preview_exported")) or bool(source_content.get("preview_exported")):
            blockers.append("source_content_preview_export_detected")
        if bool(attached_source_content.get("raw_content_exported")) or bool(cls._nested_get(attached_source_content, "content_summary", "raw_content_exported")):
            blockers.append("raw_source_content_export_detected")
        if bool(attached_source_content.get("preview_exported")) or bool(cls._nested_get(attached_source_content, "content_summary", "preview_exported")):
            blockers.append("source_content_preview_export_detected")
        if action_plan and not action_plans:
            blockers.append("source_map_consumer_action_plan_has_no_actions")
        return blockers

    @classmethod
    def _select_action_plans(cls, spec: SourceMapConsumerMaterializationSpec, action_plans: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        blockers: list[str] = []
        by_id = {str(item.get("action_id")): item for item in action_plans if isinstance(item, dict) and item.get("action_id")}
        selected = list(action_plans)
        if spec.requested_action_ids:
            missing = [action_id for action_id in spec.requested_action_ids if action_id not in by_id]
            if missing:
                blockers.extend(f"requested_action_id_not_found:{action_id}" for action_id in missing)
            selected = [by_id[action_id] for action_id in spec.requested_action_ids if action_id in by_id]
        if spec.requested_consumers:
            requested = set(spec.requested_consumers)
            selected = [item for item in selected if str(item.get("consumer")) in requested]
        blocked_selected = [str(item.get("action_id")) for item in selected if cls._status(item) not in {"ready_for_review", "ready"}]
        blockers.extend(f"selected_action_not_ready:{action_id}" for action_id in blocked_selected)
        if not selected and not blockers:
            blockers.append("no_source_map_consumer_action_selected")
        return selected, blockers

    @classmethod
    def _materialize(cls, plan: dict[str, Any], spec: SourceMapConsumerMaterializationSpec) -> dict[str, Any]:
        action_id = str(plan.get("action_id") or "")
        consumer = str(plan.get("consumer") or "")
        evidence = plan.get("evidence") if isinstance(plan.get("evidence"), dict) else {}
        base = {
            "action_id": action_id,
            "consumer": consumer,
            "source_action_status": cls._status(plan),
            "status": "ready_for_review",
            "review_required": True,
            "plan_only": True,
            "execute_automatically": False,
            "required_inputs": cls._string_list(plan.get("required_inputs")),
            "source_next_action": plan.get("next_action") or "",
            "side_effect_policy": cls._side_effect_policy(),
        }
        if consumer == "debugger":
            debugger_location = {
                "source": evidence.get("source") or cls._nested_get(spec.source_map_lookup, "location", "source") or "",
                "line_number": evidence.get("line_number") if evidence.get("line_number") is not None else cls._nested_get(spec.source_map_lookup, "location", "line_number"),
                "column_number": evidence.get("column_number") if evidence.get("column_number") is not None else cls._nested_get(spec.source_map_lookup, "location", "column_number"),
                "mapping_strategy": evidence.get("mapping_strategy") or cls._nested_get(spec.source_map_lookup, "location", "strategy") or "",
            }
            base.update(
                {
                    "materialization_kind": "debugger_location_materialization",
                    "debugger_location": debugger_location,
                    "typed_review_payload": cls._typed_payload(
                        action_id=action_id,
                        consumer=consumer,
                        payload_kind="debugger-location-review",
                        executor_input={
                            "location": debugger_location,
                            "cdp_command": None,
                            "requires_review_before_debugger_use": True,
                        },
                    ),
                    "cdp_command": None,
                    "debugger_execution_supported": False,
                    "next_action": "review_debugger_location_materialization_before_cdp_use",
                }
            )
        elif consumer == "source-logpoint":
            source_logpoint_plan = {
                "bundler_kind": evidence.get("bundler_kind") or cls._nested_get(spec.bundler_symbol_scope, "bundler_classification", "bundler_kind") or "unknown",
                "scope_candidate_count": cls._intish(evidence.get("scope_candidate_count") if evidence.get("scope_candidate_count") is not None else spec.bundler_symbol_scope.get("scope_candidate_count")),
                "install_supported": False,
                "logpoint_installed": False,
            }
            base.update(
                {
                    "materialization_kind": "source_logpoint_materialization",
                    "source_logpoint_plan": source_logpoint_plan,
                    "typed_review_payload": cls._typed_payload(
                        action_id=action_id,
                        consumer=consumer,
                        payload_kind="source-logpoint-plan-review",
                        executor_input={
                            "source_logpoint_plan": source_logpoint_plan,
                            "source_logpoint_spec_input": {
                                "url_pattern_required": True,
                                "log_expression_required": True,
                                "install_supported_now": False,
                            },
                        },
                    ),
                    "next_action": "review_source_logpoint_materialization_before_installation",
                }
            )
        elif consumer == "rebuild":
            rebuild_source_metadata = {
                "source_content_available": bool(evidence.get("source_content_available")),
                "sha256": evidence.get("sha256") or cls._nested_get(spec.source_map_source_content, "content_summary", "sha256") or "",
                "raw_content_exported": False,
                "preview_exported": False,
                "rebuild_executed": False,
            }
            base.update(
                {
                    "materialization_kind": "rebuild_source_metadata_materialization",
                    "rebuild_source_metadata": rebuild_source_metadata,
                    "typed_review_payload": cls._typed_payload(
                        action_id=action_id,
                        consumer=consumer,
                        payload_kind="rebuild-source-metadata-review",
                        executor_input={
                            "source_content_digest": rebuild_source_metadata["sha256"],
                            "source_content_available": rebuild_source_metadata["source_content_available"],
                            "raw_source_content": None,
                            "raw_content_exported": False,
                            "preview_exported": False,
                        },
                    ),
                    "next_action": "review_rebuild_source_metadata_materialization_before_rebuild_use",
                }
            )
        elif consumer == "hook":
            hook_symbol_scope = {
                "bundler_kind": evidence.get("bundler_kind") or cls._nested_get(spec.bundler_symbol_scope, "bundler_classification", "bundler_kind") or "unknown",
                "scope_candidate_count": cls._intish(evidence.get("scope_candidate_count") if evidence.get("scope_candidate_count") is not None else spec.bundler_symbol_scope.get("scope_candidate_count")),
                "hook_installed": False,
            }
            base.update(
                {
                    "materialization_kind": "hook_symbol_scope_materialization",
                    "hook_symbol_scope": hook_symbol_scope,
                    "typed_review_payload": cls._typed_payload(
                        action_id=action_id,
                        consumer=consumer,
                        payload_kind="hook-symbol-scope-review",
                        executor_input={
                            "hook_symbol_scope": hook_symbol_scope,
                            "hook_candidate_review_required": True,
                            "hook_install_supported_now": False,
                        },
                    ),
                    "next_action": "review_hook_symbol_scope_materialization_before_runtime_hook_planning",
                }
            )
        else:
            base.update(
                {
                    "materialization_kind": "unsupported_consumer_materialization",
                    "status": "blocked",
                    "blockers": ["unsupported_consumer"],
                    "next_action": "choose_supported_source_map_consumer_action",
                }
            )
        return base

    @classmethod
    def _typed_payload(cls, *, action_id: str, consumer: str, payload_kind: str, executor_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "payload_kind": payload_kind,
            "action_id": action_id,
            "consumer": consumer,
            "status": "ready_for_review",
            "review_required": True,
            "execute_automatically": False,
            "executor_input": executor_input,
            "safety": {
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "debugger_execution_performed": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
            "next_action": f"review_{payload_kind.replace('-', '_')}_before_execution",
        }

    @staticmethod
    def _materialization_blockers(materializations: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        for item in materializations:
            if item.get("status") in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append(f"materialization_not_ready:{item.get('action_id')}")
            policy = item.get("side_effect_policy") if isinstance(item.get("side_effect_policy"), dict) else {}
            if policy.get("raw_source_content_exported") or policy.get("preview_exported"):
                blockers.append("unsafe_materialization_source_content_export")
            if policy.get("cdp_command_sent") or policy.get("runtime_evaluated") or policy.get("logpoint_installed") or policy.get("hook_installed") or policy.get("rebuild_executed"):
                blockers.append("unsafe_materialization_side_effect_detected")
        return blockers

    @classmethod
    def _warnings(cls, spec: SourceMapConsumerMaterializationSpec, action_plan: dict[str, Any], selected: list[dict[str, Any]], materializations: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        warnings.extend(f"source_map_consumer_action_plan:{item}" for item in cls._string_list(action_plan.get("warnings")))
        if selected:
            warnings.append("source_map_consumer_materializations_require_explicit_review")
        if materializations:
            warnings.append("materialization_does_not_execute_debugger_logpoint_hook_or_rebuild")
        if not spec.source_map_lookup:
            warnings.append("source_map_lookup_descriptor_not_attached")
        if not spec.source_map_source_content:
            warnings.append("source_map_source_content_descriptor_not_attached")
        if not spec.bundler_symbol_scope:
            warnings.append("bundler_symbol_scope_descriptor_not_attached")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], materializations: list[dict[str, Any]]) -> str:
        if "source_map_consumer_action_plan_missing" in blockers:
            return "provide_ready_source_map_consumer_action_plan_descriptor"
        if "source_map_consumer_action_plan_not_ready" in blockers:
            return "resolve_source_map_consumer_action_plan_blockers"
        if "raw_source_content_export_detected" in blockers or "source_content_preview_export_detected" in blockers:
            return "replace_source_content_descriptor_with_metadata_only_version"
        if any(item.startswith("requested_action_id_not_found:") for item in blockers):
            return "choose_action_ids_from_source_map_consumer_action_plan"
        if "no_source_map_consumer_action_selected" in blockers or "source_map_consumer_action_plan_has_no_actions" in blockers:
            return "provide_ready_source_map_consumer_action_plan_descriptor"
        return "review_source_map_consumer_materialization_before_debugger_rebuild_logpoint_or_hook_execution"

    @staticmethod
    def _action_plans(action_plan: dict[str, Any]) -> list[dict[str, Any]]:
        items = action_plan.get("action_plans") if isinstance(action_plan.get("action_plans"), list) else []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _string_list(payload: Any) -> list[str]:
        if not isinstance(payload, list):
            return []
        return [str(item) for item in payload if str(item).strip()]

    @staticmethod
    def _intish(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapTypedPayloadPreflightSpec:
    """Review-only preflight for Source Map typed consumer payload follow-through.

    The descriptor consumes Step 270 typed review payloads and verifies that they
    are coherent inputs for future debugger, source-logpoint, rebuild, or hook
    review surfaces. It never executes those surfaces.
    """

    source_map_consumer_materialization: dict[str, Any] = field(default_factory=dict)
    typed_review_payloads: list[dict[str, Any]] = field(default_factory=list)
    requested_action_ids: tuple[str, ...] = ()
    requested_consumers: tuple[str, ...] = ()

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapTypedPayloadPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_typed_payload_preflight",
                "sourceMapTypedPayloadPreflight",
                "source_map_consumer_typed_payload_preflight",
                "sourceMapConsumerTypedPayloadPreflight",
                "source_map_followthrough_preflight",
                "sourceMapFollowthroughPreflight",
            )
        )
        materialization = cls._object_alias(
            context,
            "source_map_consumer_materialization",
            "source-map-consumer-materialization",
            "sourceMapConsumerMaterialization",
            "source_map_materialization",
            "sourceMapMaterialization",
        )
        payloads = cls._payload_list_alias(
            context,
            "typed_review_payloads",
            "typedReviewPayloads",
            "source_map_typed_review_payloads",
            "sourceMapTypedReviewPayloads",
        )
        if not payloads and materialization:
            raw_payloads = materialization.get("typed_review_payloads")
            if isinstance(raw_payloads, list):
                payloads = [item for item in raw_payloads if isinstance(item, dict)]
        if not requested and not materialization and not payloads:
            return None
        return cls(
            source_map_consumer_materialization=materialization,
            typed_review_payloads=payloads,
            requested_action_ids=cls._coerce_string_tuple(
                context.get(
                    "source_map_typed_payload_action_ids",
                    context.get("sourceMapTypedPayloadActionIds", context.get("requested_action_ids", context.get("requestedActionIds"))),
                )
            ),
            requested_consumers=cls._coerce_consumers(
                context.get(
                    "source_map_typed_payload_consumers",
                    context.get("sourceMapTypedPayloadConsumers", context.get("source_map_consumers", context.get("sourceMapConsumers"))),
                )
            ),
        )

    @classmethod
    def _object_alias(cls, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {}

    @classmethod
    def _payload_list_alias(cls, payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, dict)]
        return []

    @staticmethod
    def _coerce_string_tuple(payload: Any) -> tuple[str, ...]:
        if payload is None:
            return ()
        if isinstance(payload, str):
            raw_items = [item.strip() for item in payload.replace(";", ",").split(",")]
        elif isinstance(payload, (list, tuple, set)):
            raw_items = [str(item).strip() for item in payload]
        else:
            raw_items = []
        normalized: list[str] = []
        for item in raw_items:
            if item and item not in normalized:
                normalized.append(item)
        return tuple(normalized)

    @staticmethod
    def _coerce_consumers(payload: Any) -> tuple[str, ...]:
        if payload is None:
            return ()
        if isinstance(payload, str):
            raw_items = [item.strip() for item in payload.replace(";", ",").split(",")]
        elif isinstance(payload, (list, tuple, set)):
            raw_items = [str(item).strip() for item in payload]
        else:
            raw_items = []
        aliases = {
            "source_logpoint": "source-logpoint",
            "source-logpoints": "source-logpoint",
            "logpoint": "source-logpoint",
            "logpoints": "source-logpoint",
            "debugger-location": "debugger",
            "debugger_location": "debugger",
            "rebuild-source": "rebuild",
            "rebuild_source": "rebuild",
            "symbol-scope": "hook",
            "symbol_scope": "hook",
        }
        normalized: list[str] = []
        for item in raw_items:
            key = aliases.get(item.lower().replace(" ", "-"), item.lower().replace(" ", "-"))
            if key in {"debugger", "source-logpoint", "rebuild", "hook"} and key not in normalized:
                normalized.append(key)
        return tuple(normalized)


@dataclass(slots=True)
class SourceMapTypedPayloadPreflightResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapTypedPayloadPreflightManager:
    """Preflight Step 270 typed review payloads for later explicit follow-through."""

    def review(self, spec: SourceMapTypedPayloadPreflightSpec | None) -> SourceMapTypedPayloadPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapTypedPayloadPreflightResult(status="unsupported", reason="missing_source_map_typed_payload_preflight_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapTypedPayloadPreflightResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_typed_payload_preflight_failed")
            descriptor["error"] = str(exc)
            return SourceMapTypedPayloadPreflightResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_typed_payload_preflight_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapTypedPayloadPreflightSpec) -> dict[str, Any]:
        materialization = spec.source_map_consumer_materialization
        payloads = [item for item in spec.typed_review_payloads if isinstance(item, dict)]
        blockers = self._input_blockers(materialization, payloads)
        selected, selection_blockers = self._select_payloads(spec, payloads)
        blockers.extend(selection_blockers)
        preflights = [] if blockers else [self._preflight_payload(item) for item in selected]
        blockers.extend(self._preflight_blockers(preflights))
        warnings = self._warnings(materialization, selected, preflights)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-typed-payload-preflight.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "preflight_only": True,
            "typed_payload_schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "source_materialization_status": self._status(materialization),
            "source_materialization_schema_version": str(materialization.get("schema_version") or ""),
            "requested_action_ids": list(spec.requested_action_ids),
            "requested_consumers": list(spec.requested_consumers),
            "typed_payload_count": len(payloads),
            "selected_action_ids": [str(item.get("action_id")) for item in selected if item.get("action_id")],
            "selected_consumers": sorted({str(item.get("consumer")) for item in selected if item.get("consumer")}),
            "preflight_payloads": preflights,
            "preflight_payload_count": len(preflights),
            "ready_for_followthrough_review": bool(preflights) and not blockers,
            "followthrough_executor_invoked": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, preflights),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-typed-payload-preflight.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "preflight_only": True,
            "reason": reason,
            "typed_payload_schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "source_materialization_status": "",
            "source_materialization_schema_version": "",
            "requested_action_ids": [],
            "requested_consumers": [],
            "typed_payload_count": 0,
            "selected_action_ids": [],
            "selected_consumers": [],
            "preflight_payloads": [],
            "preflight_payload_count": 0,
            "ready_for_followthrough_review": False,
            "followthrough_executor_invoked": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_consumer_materialization_with_typed_payloads",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, materialization: dict[str, Any], payloads: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        if not materialization and not payloads:
            blockers.append("source_map_typed_payloads_missing")
        if materialization:
            if cls._status(materialization) in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_consumer_materialization_not_ready")
            blockers.extend(f"source_map_consumer_materialization:{item}" for item in cls._string_list(materialization.get("blockers")))
            if materialization.get("typed_payload_schema_version") not in {None, "", "reverse-deepagent.source-map-consumer-typed-review-payload.v1"}:
                blockers.append("typed_payload_schema_version_mismatch")
            policy = materialization.get("side_effect_policy") if isinstance(materialization.get("side_effect_policy"), dict) else {}
            blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_consumer_materialization"))
        if not payloads:
            blockers.append("typed_review_payloads_missing")
        return blockers

    @classmethod
    def _select_payloads(cls, spec: SourceMapTypedPayloadPreflightSpec, payloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        blockers: list[str] = []
        by_id = {str(item.get("action_id")): item for item in payloads if isinstance(item, dict) and item.get("action_id")}
        selected = list(payloads)
        if spec.requested_action_ids:
            missing = [action_id for action_id in spec.requested_action_ids if action_id not in by_id]
            blockers.extend(f"requested_typed_payload_action_id_not_found:{action_id}" for action_id in missing)
            selected = [by_id[action_id] for action_id in spec.requested_action_ids if action_id in by_id]
        if spec.requested_consumers:
            requested = set(spec.requested_consumers)
            selected = [item for item in selected if str(item.get("consumer")) in requested]
        if not selected and not blockers:
            blockers.append("no_source_map_typed_payload_selected")
        return selected, blockers

    @classmethod
    def _preflight_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        consumer = str(payload.get("consumer") or "")
        payload_kind = str(payload.get("payload_kind") or "")
        executor_input = payload.get("executor_input") if isinstance(payload.get("executor_input"), dict) else {}
        blockers: list[str] = []
        if payload.get("schema_version") != "reverse-deepagent.source-map-consumer-typed-review-payload.v1":
            blockers.append("typed_payload_schema_version_mismatch")
        if cls._status(payload) not in {"ready_for_review", "ready"}:
            blockers.append("typed_payload_not_ready")
        if payload.get("review_required") is not True:
            blockers.append("typed_payload_review_required_missing")
        if payload.get("execute_automatically") is True:
            blockers.append("typed_payload_auto_execution_claim_detected")
        blockers.extend(cls._side_effect_blockers(payload.get("safety") if isinstance(payload.get("safety"), dict) else {}, prefix="typed_payload"))
        if consumer == "debugger":
            blockers.extend(cls._debugger_blockers(payload_kind, executor_input))
            followthrough = "review_debugger_location_executor_input"
        elif consumer == "source-logpoint":
            blockers.extend(cls._source_logpoint_blockers(payload_kind, executor_input))
            followthrough = "review_source_logpoint_executor_input"
        elif consumer == "rebuild":
            blockers.extend(cls._rebuild_blockers(payload_kind, executor_input))
            followthrough = "review_rebuild_source_metadata_executor_input"
        elif consumer == "hook":
            blockers.extend(cls._hook_blockers(payload_kind, executor_input))
            followthrough = "review_hook_symbol_scope_executor_input"
        else:
            blockers.append("unsupported_typed_payload_consumer")
            followthrough = "choose_supported_source_map_typed_payload_consumer"
        return {
            "action_id": str(payload.get("action_id") or ""),
            "consumer": consumer,
            "payload_kind": payload_kind,
            "status": "blocked" if blockers else "ready_for_review",
            "review_required": True,
            "preflight_only": True,
            "execute_automatically": False,
            "ready_for_followthrough_review": not blockers,
            "followthrough_review_surface": followthrough,
            "executor_input": executor_input,
            "executor_invoked": False,
            "blockers": list(dict.fromkeys(blockers)),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _debugger_blockers(payload_kind: str, executor_input: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        location = executor_input.get("location") if isinstance(executor_input.get("location"), dict) else {}
        if payload_kind != "debugger-location-review":
            blockers.append("debugger_payload_kind_mismatch")
        if not location:
            blockers.append("debugger_location_missing")
        if executor_input.get("cdp_command") is not None:
            blockers.append("debugger_cdp_command_must_be_absent")
        if executor_input.get("requires_review_before_debugger_use") is not True:
            blockers.append("debugger_review_gate_missing")
        return blockers

    @staticmethod
    def _source_logpoint_blockers(payload_kind: str, executor_input: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        spec_input = executor_input.get("source_logpoint_spec_input") if isinstance(executor_input.get("source_logpoint_spec_input"), dict) else {}
        if payload_kind != "source-logpoint-plan-review":
            blockers.append("source_logpoint_payload_kind_mismatch")
        if not isinstance(executor_input.get("source_logpoint_plan"), dict):
            blockers.append("source_logpoint_plan_missing")
        if spec_input.get("install_supported_now") is True:
            blockers.append("source_logpoint_install_claim_detected")
        if spec_input.get("url_pattern_required") is not True or spec_input.get("log_expression_required") is not True:
            blockers.append("source_logpoint_review_inputs_incomplete")
        return blockers

    @staticmethod
    def _rebuild_blockers(payload_kind: str, executor_input: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if payload_kind != "rebuild-source-metadata-review":
            blockers.append("rebuild_payload_kind_mismatch")
        if not executor_input.get("source_content_digest"):
            blockers.append("rebuild_source_content_digest_missing")
        if executor_input.get("raw_source_content") is not None or executor_input.get("raw_content_exported") is True:
            blockers.append("rebuild_raw_source_export_claim_detected")
        if executor_input.get("preview_exported") is True:
            blockers.append("rebuild_preview_export_claim_detected")
        return blockers

    @staticmethod
    def _hook_blockers(payload_kind: str, executor_input: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if payload_kind != "hook-symbol-scope-review":
            blockers.append("hook_payload_kind_mismatch")
        if not isinstance(executor_input.get("hook_symbol_scope"), dict):
            blockers.append("hook_symbol_scope_missing")
        if executor_input.get("hook_candidate_review_required") is not True:
            blockers.append("hook_review_gate_missing")
        if executor_input.get("hook_install_supported_now") is True:
            blockers.append("hook_install_claim_detected")
        return blockers

    @classmethod
    def _preflight_blockers(cls, preflights: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        for item in preflights:
            if item.get("status") in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append(f"typed_payload_preflight_not_ready:{item.get('action_id')}")
        return blockers

    @classmethod
    def _warnings(cls, materialization: dict[str, Any], selected: list[dict[str, Any]], preflights: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        warnings.extend(f"source_map_consumer_materialization:{item}" for item in cls._string_list(materialization.get("warnings")))
        if selected:
            warnings.append("source_map_typed_payloads_require_explicit_followthrough_review")
        if preflights:
            warnings.append("preflight_does_not_execute_debugger_logpoint_hook_or_rebuild")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], preflights: list[dict[str, Any]]) -> str:
        if "source_map_typed_payloads_missing" in blockers or "typed_review_payloads_missing" in blockers:
            return "provide_source_map_consumer_materialization_with_typed_payloads"
        if "source_map_consumer_materialization_not_ready" in blockers:
            return "resolve_source_map_consumer_materialization_blockers"
        if any(item.startswith("requested_typed_payload_action_id_not_found:") for item in blockers):
            return "choose_action_ids_from_source_map_typed_payloads"
        if "no_source_map_typed_payload_selected" in blockers:
            return "select_source_map_typed_payload_for_preflight"
        if any(item.startswith("typed_payload_preflight_not_ready:") for item in blockers):
            return "fix_source_map_typed_payload_executor_input_before_followthrough_review"
        if preflights:
            return "review_source_map_typed_payload_preflight_before_explicit_debugger_logpoint_rebuild_or_hook_execution"
        return "provide_source_map_consumer_materialization_with_typed_payloads"

    @staticmethod
    def _side_effect_blockers(policy: dict[str, Any], *, prefix: str) -> list[str]:
        blockers: list[str] = []
        if policy.get("raw_source_content_exported"):
            blockers.append(f"{prefix}_raw_source_content_export_detected")
        if policy.get("preview_exported"):
            blockers.append(f"{prefix}_preview_export_detected")
        if policy.get("fetch_source_map"):
            blockers.append(f"{prefix}_source_map_fetch_detected")
        if policy.get("browser_started"):
            blockers.append(f"{prefix}_browser_start_detected")
        if policy.get("cdp_command_sent"):
            blockers.append(f"{prefix}_cdp_command_detected")
        if policy.get("debugger_execution_performed"):
            blockers.append(f"{prefix}_debugger_execution_detected")
        if policy.get("runtime_evaluated"):
            blockers.append(f"{prefix}_runtime_evaluation_detected")
        if policy.get("logpoint_installed"):
            blockers.append(f"{prefix}_logpoint_install_detected")
        if policy.get("hook_installed"):
            blockers.append(f"{prefix}_hook_install_detected")
        if policy.get("rebuild_executed"):
            blockers.append(f"{prefix}_rebuild_execution_detected")
        if policy.get("calls_mcp"):
            blockers.append(f"{prefix}_mcp_call_detected")
        if policy.get("mobile_runtime_used"):
            blockers.append(f"{prefix}_mobile_runtime_detected")
        return blockers

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _string_list(payload: Any) -> list[str]:
        if not isinstance(payload, list):
            return []
        return [str(item) for item in payload if str(item).strip()]

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "preflight_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughReviewSpec:
    """Review-only handoff descriptor for Source Map typed payload follow-through.

    The descriptor consumes the Step 271 typed-payload preflight output and
    groups ready debugger / source-logpoint / rebuild / hook review surfaces for
    a human or dedicated subagent.  It deliberately does not execute any of
    those follow-through surfaces.
    """

    source_map_typed_payload_preflight: dict[str, Any] = field(default_factory=dict)
    preflight_payloads: list[dict[str, Any]] = field(default_factory=list)
    requested_action_ids: tuple[str, ...] = ()
    requested_consumers: tuple[str, ...] = ()

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughReviewSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_review",
                "sourceMapFollowthroughReview",
                "source_map_typed_payload_followthrough_review",
                "sourceMapTypedPayloadFollowthroughReview",
                "source_map_followthrough_review_surface",
                "sourceMapFollowthroughReviewSurface",
                "source_map_consumer_followthrough_review",
                "sourceMapConsumerFollowthroughReview",
            )
        )
        preflight = cls._object_alias(
            context,
            "source_map_typed_payload_preflight",
            "source-map-typed-payload-preflight",
            "sourceMapTypedPayloadPreflight",
            "source_map_consumer_typed_payload_preflight",
            "source-map-consumer-typed-payload-preflight",
            "sourceMapConsumerTypedPayloadPreflight",
            "source_map_followthrough_preflight",
            "source-map-followthrough-preflight",
            "sourceMapFollowthroughPreflight",
        )
        payloads = cls._payload_list_alias(
            context,
            "preflight_payloads",
            "preflightPayloads",
            "source_map_preflight_payloads",
            "sourceMapPreflightPayloads",
            "source_map_followthrough_preflight_payloads",
            "sourceMapFollowthroughPreflightPayloads",
        )
        if not payloads and preflight:
            raw_payloads = preflight.get("preflight_payloads")
            if isinstance(raw_payloads, list):
                payloads = [item for item in raw_payloads if isinstance(item, dict)]
        if not requested and not preflight and not payloads:
            return None
        return cls(
            source_map_typed_payload_preflight=preflight,
            preflight_payloads=payloads,
            requested_action_ids=SourceMapTypedPayloadPreflightSpec._coerce_string_tuple(
                context.get(
                    "source_map_followthrough_action_ids",
                    context.get("sourceMapFollowthroughActionIds", context.get("requested_action_ids", context.get("requestedActionIds"))),
                )
            ),
            requested_consumers=SourceMapTypedPayloadPreflightSpec._coerce_consumers(
                context.get(
                    "source_map_followthrough_consumers",
                    context.get("sourceMapFollowthroughConsumers", context.get("source_map_consumers", context.get("sourceMapConsumers"))),
                )
            ),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)
    _payload_list_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._payload_list_alias)


@dataclass(slots=True)
class SourceMapFollowthroughReviewResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapFollowthroughReviewManager:
    """Normalize ready typed-payload preflights into explicit review handoffs."""

    def review(self, spec: SourceMapFollowthroughReviewSpec | None) -> SourceMapFollowthroughReviewResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughReviewResult(status="unsupported", reason="missing_source_map_followthrough_review_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughReviewResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_review_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughReviewResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_review_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughReviewSpec) -> dict[str, Any]:
        preflight = spec.source_map_typed_payload_preflight
        payloads = [item for item in spec.preflight_payloads if isinstance(item, dict)]
        blockers = self._input_blockers(preflight, payloads)
        selected, selection_blockers = self._select_payloads(spec, payloads)
        blockers.extend(selection_blockers)
        reviews = [] if blockers else [self._review_surface(item) for item in selected]
        blockers.extend(self._review_blockers(reviews))
        warnings = self._warnings(preflight, selected, reviews)
        status = "blocked" if blockers else "ready_for_review"
        ready_count = sum(1 for item in reviews if item.get("status") == "ready_for_review")
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-review.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "handoff_only": True,
            "source_preflight_schema_version": str(preflight.get("schema_version") or ""),
            "source_preflight_status": self._status(preflight),
            "typed_payload_schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "requested_action_ids": list(spec.requested_action_ids),
            "requested_consumers": list(spec.requested_consumers),
            "selected_action_ids": [str(item.get("action_id")) for item in selected if item.get("action_id")],
            "selected_consumers": sorted({str(item.get("consumer")) for item in selected if item.get("consumer")}),
            "followthrough_reviews": reviews,
            "followthrough_review_count": len(reviews),
            "ready_followthrough_review_count": ready_count,
            "ready_for_explicit_review": bool(reviews) and ready_count == len(reviews) and not blockers,
            "followthrough_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, reviews),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-review.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_preflight_schema_version": "",
            "source_preflight_status": "",
            "typed_payload_schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "requested_action_ids": [],
            "requested_consumers": [],
            "selected_action_ids": [],
            "selected_consumers": [],
            "followthrough_reviews": [],
            "followthrough_review_count": 0,
            "ready_followthrough_review_count": 0,
            "ready_for_explicit_review": False,
            "followthrough_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_typed_payload_preflight_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, preflight: dict[str, Any], payloads: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        if not preflight and not payloads:
            blockers.append("source_map_typed_payload_preflight_missing")
        if preflight:
            if preflight.get("schema_version") not in {None, "", "reverse-deepagent.source-map-typed-payload-preflight.v1"}:
                blockers.append("source_map_typed_payload_preflight_schema_mismatch")
            if cls._status(preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_typed_payload_preflight_not_ready")
            if preflight.get("ready_for_followthrough_review") is not True:
                blockers.append("source_map_typed_payload_preflight_not_ready_for_followthrough")
            if preflight.get("followthrough_executor_invoked") is True:
                blockers.append("source_map_typed_payload_preflight_executor_invoked")
            blockers.extend(f"source_map_typed_payload_preflight:{item}" for item in cls._string_list(preflight.get("blockers")))
            policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
            blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_typed_payload_preflight"))
        if not payloads:
            blockers.append("source_map_preflight_payloads_missing")
        return blockers

    @classmethod
    def _select_payloads(cls, spec: SourceMapFollowthroughReviewSpec, payloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        blockers: list[str] = []
        by_id = {str(item.get("action_id")): item for item in payloads if isinstance(item, dict) and item.get("action_id")}
        selected = list(payloads)
        if spec.requested_action_ids:
            missing = [action_id for action_id in spec.requested_action_ids if action_id not in by_id]
            blockers.extend(f"requested_followthrough_action_id_not_found:{action_id}" for action_id in missing)
            selected = [by_id[action_id] for action_id in spec.requested_action_ids if action_id in by_id]
        if spec.requested_consumers:
            requested = set(spec.requested_consumers)
            selected = [item for item in selected if str(item.get("consumer")) in requested]
        if not selected and not blockers:
            blockers.append("no_source_map_followthrough_payload_selected")
        return selected, blockers

    @classmethod
    def _review_surface(cls, preflight_payload: dict[str, Any]) -> dict[str, Any]:
        consumer = str(preflight_payload.get("consumer") or "")
        payload_kind = str(preflight_payload.get("payload_kind") or "")
        executor_input = preflight_payload.get("executor_input") if isinstance(preflight_payload.get("executor_input"), dict) else {}
        blockers: list[str] = []
        if cls._status(preflight_payload) not in {"ready_for_review", "ready"}:
            blockers.append("preflight_payload_not_ready")
        if preflight_payload.get("ready_for_followthrough_review") is not True:
            blockers.append("preflight_payload_not_ready_for_followthrough")
        if preflight_payload.get("review_required") is not True:
            blockers.append("preflight_payload_review_required_missing")
        if preflight_payload.get("execute_automatically") is True:
            blockers.append("preflight_payload_auto_execution_claim_detected")
        if preflight_payload.get("executor_invoked") is True:
            blockers.append("preflight_payload_executor_invoked")
        blockers.extend(cls._side_effect_blockers(preflight_payload.get("side_effect_policy") if isinstance(preflight_payload.get("side_effect_policy"), dict) else {}, prefix="preflight_payload"))
        surface, prompt, next_action = cls._surface_metadata(consumer)
        if surface == "choose_supported_source_map_followthrough_consumer":
            blockers.append("unsupported_followthrough_consumer")
        return {
            "action_id": str(preflight_payload.get("action_id") or ""),
            "consumer": consumer,
            "payload_kind": payload_kind,
            "status": "blocked" if blockers else "ready_for_review",
            "review_required": True,
            "explicit_review_required": True,
            "review_only": True,
            "plan_only": True,
            "handoff_only": True,
            "execute_automatically": False,
            "followthrough_review_surface": surface,
            "review_prompt": prompt,
            "next_action": next_action,
            "executor_input": executor_input,
            "executor_invoked": False,
            "blockers": list(dict.fromkeys(blockers)),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _surface_metadata(consumer: str) -> tuple[str, str, str]:
        if consumer == "debugger":
            return (
                "review_debugger_location_executor_input",
                "Review debugger location executor input before any CDP Debugger command.",
                "review_debugger_location_before_cdp_command",
            )
        if consumer == "source-logpoint":
            return (
                "review_source_logpoint_executor_input",
                "Review source-logpoint plan before installation.",
                "review_source_logpoint_plan_before_installation",
            )
        if consumer == "rebuild":
            return (
                "review_rebuild_source_metadata_executor_input",
                "Review digest-only rebuild metadata before generation.",
                "review_rebuild_source_metadata_before_generation",
            )
        if consumer == "hook":
            return (
                "review_hook_symbol_scope_executor_input",
                "Review hook symbol scope candidate before runtime hook installation.",
                "review_hook_symbol_scope_before_runtime_hook",
            )
        return (
            "choose_supported_source_map_followthrough_consumer",
            "Choose debugger, source-logpoint, rebuild, or hook follow-through review.",
            "choose_supported_source_map_followthrough_consumer",
        )

    @classmethod
    def _review_blockers(cls, reviews: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        for item in reviews:
            if item.get("status") in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append(f"source_map_followthrough_review_not_ready:{item.get('action_id')}")
        return blockers

    @classmethod
    def _warnings(cls, preflight: dict[str, Any], selected: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        warnings.extend(f"source_map_typed_payload_preflight:{item}" for item in cls._string_list(preflight.get("warnings")))
        if selected and not preflight:
            warnings.append("source_map_followthrough_review_uses_explicit_preflight_payloads")
        if reviews:
            warnings.append("source_map_followthrough_surfaces_require_explicit_review")
            warnings.append("followthrough_review_does_not_execute_debugger_logpoint_hook_or_rebuild")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], reviews: list[dict[str, Any]]) -> str:
        if "source_map_typed_payload_preflight_missing" in blockers or "source_map_preflight_payloads_missing" in blockers:
            return "provide_ready_source_map_typed_payload_preflight_descriptor"
        if (
            "source_map_typed_payload_preflight_not_ready" in blockers
            or "source_map_typed_payload_preflight_not_ready_for_followthrough" in blockers
            or any(item.startswith("source_map_typed_payload_preflight_") for item in blockers)
            or any(item.startswith("source_map_typed_payload_preflight:") for item in blockers)
        ):
            return "resolve_source_map_typed_payload_preflight_blockers"
        if any(item.startswith("requested_followthrough_action_id_not_found:") for item in blockers):
            return "choose_action_ids_from_source_map_typed_payload_preflight"
        if "no_source_map_followthrough_payload_selected" in blockers:
            return "select_source_map_followthrough_payload_for_review"
        if any(item.startswith("source_map_followthrough_review_not_ready:") for item in blockers):
            return "fix_source_map_followthrough_review_inputs"
        if reviews:
            return "choose_explicit_source_map_followthrough_review_surface"
        return "provide_ready_source_map_typed_payload_preflight_descriptor"

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "followthrough_executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughSurfaceSelectionSpec:
    """Review-only selector for one Source Map follow-through review surface.

    The descriptor consumes the Step 272 follow-through review handoff and
    selects exactly one debugger / source-logpoint / rebuild / hook review item
    for a downstream explicit review.  It is still not an executor.
    """

    source_map_followthrough_review: dict[str, Any] = field(default_factory=dict)
    followthrough_reviews: list[dict[str, Any]] = field(default_factory=list)
    requested_action_ids: tuple[str, ...] = ()
    requested_consumers: tuple[str, ...] = ()
    requested_surfaces: tuple[str, ...] = ()

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughSurfaceSelectionSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_surface_selection",
                "sourceMapFollowthroughSurfaceSelection",
                "source_map_followthrough_surface_review",
                "sourceMapFollowthroughSurfaceReview",
                "source_map_followthrough_surface_selector",
                "sourceMapFollowthroughSurfaceSelector",
            )
        )
        review = cls._object_alias(
            context,
            "source_map_followthrough_review",
            "source-map-followthrough-review",
            "sourceMapFollowthroughReview",
            "source_map_typed_payload_followthrough_review",
            "source-map-typed-payload-followthrough-review",
            "sourceMapTypedPayloadFollowthroughReview",
            "source_map_consumer_followthrough_review",
            "source-map-consumer-followthrough-review",
            "sourceMapConsumerFollowthroughReview",
        )
        reviews = cls._payload_list_alias(
            context,
            "followthrough_reviews",
            "followthroughReviews",
            "source_map_followthrough_reviews",
            "sourceMapFollowthroughReviews",
            "source_map_followthrough_review_items",
            "sourceMapFollowthroughReviewItems",
        )
        if not reviews and review:
            raw_reviews = review.get("followthrough_reviews")
            if isinstance(raw_reviews, list):
                reviews = [item for item in raw_reviews if isinstance(item, dict)]
        if not requested and not review and not reviews:
            return None
        return cls(
            source_map_followthrough_review=review,
            followthrough_reviews=reviews,
            requested_action_ids=SourceMapTypedPayloadPreflightSpec._coerce_string_tuple(
                context.get(
                    "source_map_followthrough_surface_action_ids",
                    context.get(
                        "sourceMapFollowthroughSurfaceActionIds",
                        context.get("source_map_followthrough_action_ids", context.get("requested_action_ids", context.get("requestedActionIds"))),
                    ),
                )
            ),
            requested_consumers=SourceMapTypedPayloadPreflightSpec._coerce_consumers(
                context.get(
                    "source_map_followthrough_surface_consumers",
                    context.get(
                        "sourceMapFollowthroughSurfaceConsumers",
                        context.get("source_map_followthrough_consumers", context.get("source_map_consumers", context.get("sourceMapConsumers"))),
                    ),
                )
            ),
            requested_surfaces=cls._coerce_surfaces(
                context.get(
                    "source_map_followthrough_surfaces",
                    context.get("sourceMapFollowthroughSurfaces", context.get("followthrough_review_surfaces", context.get("followthroughReviewSurfaces"))),
                )
            ),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)
    _payload_list_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._payload_list_alias)

    @staticmethod
    def _coerce_surfaces(payload: Any) -> tuple[str, ...]:
        if payload is None:
            return ()
        if isinstance(payload, str):
            raw_items = [item.strip() for item in payload.replace(";", ",").split(",")]
        elif isinstance(payload, (list, tuple, set)):
            raw_items = [str(item).strip() for item in payload]
        else:
            raw_items = []
        normalized: list[str] = []
        for item in raw_items:
            if item and item not in normalized:
                normalized.append(item)
        return tuple(normalized)


@dataclass(slots=True)
class SourceMapFollowthroughSurfaceSelectionResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapFollowthroughSurfaceSelectionManager:
    """Select one reviewed Source Map follow-through surface without executing it."""

    def review(self, spec: SourceMapFollowthroughSurfaceSelectionSpec | None) -> SourceMapFollowthroughSurfaceSelectionResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughSurfaceSelectionResult(status="unsupported", reason="missing_source_map_followthrough_surface_selection_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughSurfaceSelectionResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_surface_selection_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughSurfaceSelectionResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_surface_selection_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughSurfaceSelectionSpec) -> dict[str, Any]:
        review = spec.source_map_followthrough_review
        reviews = [item for item in spec.followthrough_reviews if isinstance(item, dict)]
        blockers = self._input_blockers(review, reviews)
        selected, selection_blockers = self._select_review(spec, reviews)
        blockers.extend(selection_blockers)
        if selected:
            blockers.extend(self._selected_review_blockers(selected))
        warnings = self._warnings(review, selected)
        status = "blocked" if blockers else "ready_for_review"
        selected_review = selected or {}
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-surface-selection.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "source_followthrough_review_schema_version": str(review.get("schema_version") or ""),
            "source_followthrough_review_status": self._status(review),
            "requested_action_ids": list(spec.requested_action_ids),
            "requested_consumers": list(spec.requested_consumers),
            "requested_surfaces": list(spec.requested_surfaces),
            "candidate_review_count": len(reviews),
            "selected_action_id": str(selected_review.get("action_id") or ""),
            "selected_consumer": str(selected_review.get("consumer") or ""),
            "selected_followthrough_review_surface": str(selected_review.get("followthrough_review_surface") or ""),
            "selected_review": selected_review,
            "selected_executor_input": selected_review.get("executor_input") if isinstance(selected_review.get("executor_input"), dict) else {},
            "downstream_review_prompt": str(selected_review.get("review_prompt") or ""),
            "downstream_next_action": str(selected_review.get("next_action") or ""),
            "ready_for_surface_review": bool(selected) and not blockers,
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, selected_review),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-surface-selection.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_followthrough_review_schema_version": "",
            "source_followthrough_review_status": "",
            "requested_action_ids": [],
            "requested_consumers": [],
            "requested_surfaces": [],
            "candidate_review_count": 0,
            "selected_action_id": "",
            "selected_consumer": "",
            "selected_followthrough_review_surface": "",
            "selected_review": {},
            "selected_executor_input": {},
            "downstream_review_prompt": "",
            "downstream_next_action": "",
            "ready_for_surface_review": False,
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_review_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, review: dict[str, Any], reviews: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        if not review and not reviews:
            blockers.append("source_map_followthrough_review_missing")
        if review:
            if review.get("schema_version") not in {None, "", "reverse-deepagent.source-map-followthrough-review.v1"}:
                blockers.append("source_map_followthrough_review_schema_mismatch")
            if cls._status(review) in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_followthrough_review_not_ready")
            if review.get("ready_for_explicit_review") is not True:
                blockers.append("source_map_followthrough_review_not_ready_for_surface_selection")
            if review.get("followthrough_executor_invoked") is True:
                blockers.append("source_map_followthrough_review_executor_invoked")
            blockers.extend(f"source_map_followthrough_review:{item}" for item in cls._string_list(review.get("blockers")))
            policy = review.get("side_effect_policy") if isinstance(review.get("side_effect_policy"), dict) else {}
            blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_followthrough_review"))
        if not reviews:
            blockers.append("source_map_followthrough_reviews_missing")
        return blockers

    @classmethod
    def _select_review(cls, spec: SourceMapFollowthroughSurfaceSelectionSpec, reviews: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
        blockers: list[str] = []
        selected = list(reviews)
        if spec.requested_action_ids:
            if len(spec.requested_action_ids) != 1:
                blockers.append("exactly_one_followthrough_action_id_required")
            by_id = {str(item.get("action_id")): item for item in reviews if isinstance(item, dict) and item.get("action_id")}
            missing = [action_id for action_id in spec.requested_action_ids if action_id not in by_id]
            blockers.extend(f"requested_followthrough_action_id_not_found:{action_id}" for action_id in missing)
            selected = [by_id[action_id] for action_id in spec.requested_action_ids if action_id in by_id]
        if spec.requested_consumers:
            selected = [item for item in selected if str(item.get("consumer")) in set(spec.requested_consumers)]
        if spec.requested_surfaces:
            selected = [item for item in selected if str(item.get("followthrough_review_surface")) in set(spec.requested_surfaces)]
        selector_provided = bool(spec.requested_action_ids or spec.requested_consumers or spec.requested_surfaces)
        if not selector_provided and len(selected) > 1:
            blockers.append("source_map_followthrough_surface_selector_missing")
        if not selected and not blockers:
            blockers.append("no_source_map_followthrough_surface_selected")
        if len(selected) > 1 and not blockers:
            blockers.append("source_map_followthrough_surface_selection_ambiguous")
        return (selected[0] if len(selected) == 1 else {}), blockers

    @classmethod
    def _selected_review_blockers(cls, selected: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if cls._status(selected) not in {"ready_for_review", "ready"}:
            blockers.append("selected_followthrough_review_not_ready")
        if selected.get("explicit_review_required") is not True:
            blockers.append("selected_followthrough_explicit_review_required_missing")
        if selected.get("execute_automatically") is True:
            blockers.append("selected_followthrough_auto_execution_claim_detected")
        if selected.get("executor_invoked") is True:
            blockers.append("selected_followthrough_executor_invoked")
        blockers.extend(cls._side_effect_blockers(selected.get("side_effect_policy") if isinstance(selected.get("side_effect_policy"), dict) else {}, prefix="selected_followthrough_review"))
        if not isinstance(selected.get("executor_input"), dict) or not selected.get("executor_input"):
            blockers.append("selected_followthrough_executor_input_missing")
        if not selected.get("followthrough_review_surface"):
            blockers.append("selected_followthrough_review_surface_missing")
        return blockers

    @classmethod
    def _warnings(cls, review: dict[str, Any], selected: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        warnings.extend(f"source_map_followthrough_review:{item}" for item in cls._string_list(review.get("warnings")))
        if selected:
            warnings.append("source_map_followthrough_surface_requires_explicit_downstream_review")
            warnings.append("surface_selection_does_not_execute_debugger_logpoint_hook_or_rebuild")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], selected: dict[str, Any]) -> str:
        if "source_map_followthrough_review_missing" in blockers or "source_map_followthrough_reviews_missing" in blockers:
            return "provide_ready_source_map_followthrough_review_descriptor"
        if (
            "source_map_followthrough_review_not_ready" in blockers
            or "source_map_followthrough_review_not_ready_for_surface_selection" in blockers
            or any(item.startswith("source_map_followthrough_review_") for item in blockers)
            or any(item.startswith("source_map_followthrough_review:") for item in blockers)
        ):
            return "resolve_source_map_followthrough_review_blockers"
        if any(item.startswith("requested_followthrough_action_id_not_found:") for item in blockers):
            return "choose_action_id_from_source_map_followthrough_reviews"
        if "source_map_followthrough_surface_selector_missing" in blockers or "source_map_followthrough_surface_selection_ambiguous" in blockers:
            return "choose_one_source_map_followthrough_surface"
        if "no_source_map_followthrough_surface_selected" in blockers:
            return "select_source_map_followthrough_surface_for_review"
        if blockers:
            return "fix_selected_source_map_followthrough_surface_before_review"
        if selected:
            return str(selected.get("next_action") or "review_selected_source_map_followthrough_surface_before_execution")
        return "provide_ready_source_map_followthrough_review_descriptor"

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class BundlerSymbolScopeSpec:
    """Review-only descriptor request for Source Map symbol scope hints.

    The descriptor consumes caller-provided Source Map payloads and optional
    runtime inventory hints.  It never fetches Source Maps, starts a browser,
    evaluates JavaScript, installs logpoints, or calls MCP.  Its job is to turn
    conservative Source Map / bundler metadata into reviewable hook and
    source-logpoint readiness hints.
    """

    source_map: dict[str, Any] | None = None
    source_map_fetch_result: dict[str, Any] = field(default_factory=dict)
    script_url: str = ""
    script_source: str = ""
    original_source: str = ""
    symbol_name: str = ""
    original_line_number: int | None = None
    original_column_number: int = 0
    source_map_bias: str = "greatest_lower_bound"
    module_candidates: list[dict[str, Any]] = field(default_factory=list)
    script_inventory: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "BundlerSymbolScopeSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "bundler_symbol_scope",
                "bundlerSymbolScope",
                "source_map_symbol_scope",
                "sourceMapSymbolScope",
                "review_bundler_symbol_scope",
                "reviewBundlerSymbolScope",
            )
        )
        source_map = cls._coerce_source_map(context.get("source_map", context.get("sourceMap")))
        source_map_fetch_result = cls._coerce_dict(
            context.get("source_map_fetch_result", context.get("sourceMapFetchResult", context.get("source-map-fetch-result")))
        )
        symbol_name = str(context.get("symbol_name", context.get("symbolName", context.get("function_name", context.get("functionName", "")))) or "")
        original_source = str(context.get("original_source", context.get("originalSource", context.get("source", ""))) or "")
        if not requested and source_map is None:
            return None
        original_line = context.get("original_line", context.get("originalLine", context.get("original_line_number", context.get("originalLineNumber"))))
        original_column = context.get("original_column", context.get("originalColumn", context.get("original_column_number", context.get("originalColumnNumber", 0))))
        line_base = int(context.get("original_line_base", context.get("originalLineBase", 0)) or 0)
        column_base = int(context.get("original_column_base", context.get("originalColumnBase", 0)) or 0)
        return cls(
            source_map=source_map,
            source_map_fetch_result=source_map_fetch_result,
            script_url=str(context.get("script_url", context.get("scriptUrl", context.get("url", ""))) or ""),
            script_source=str(context.get("script_source", context.get("scriptSource", context.get("bundle_source", context.get("bundleSource", "")))) or ""),
            original_source=original_source,
            symbol_name=symbol_name,
            original_line_number=(int(original_line) - line_base) if original_line is not None else None,
            original_column_number=int(original_column or 0) - column_base,
            source_map_bias=str(context.get("source_map_bias", context.get("sourceMapBias", "greatest_lower_bound")) or "greatest_lower_bound"),
            module_candidates=cls._coerce_dict_list(context.get("module_candidates", context.get("moduleCandidates", []))),
            script_inventory=cls._coerce_dict_list(context.get("script_inventory", context.get("scriptInventory", []))),
        )

    @staticmethod
    def _coerce_source_map(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
        return None

    @staticmethod
    def _coerce_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _coerce_dict_list(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, str) and value.strip():
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]


@dataclass(slots=True)
class BundlerSymbolScopeResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class BundlerSymbolScopeManager:
    """Build a review-only Source Map / bundler symbol-scope descriptor."""

    def review(self, spec: BundlerSymbolScopeSpec | None) -> BundlerSymbolScopeResult:
        policy = self._side_effect_policy()
        if spec is None:
            return BundlerSymbolScopeResult(status="unsupported", reason="missing_bundler_symbol_scope_request", side_effect_policy=policy)
        if not isinstance(spec.source_map, dict):
            descriptor = self._base_descriptor(spec, status="blocked", reason="missing_source_map_payload")
            return BundlerSymbolScopeResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_source_map_payload")
        try:
            descriptor = self._descriptor(spec)
            return BundlerSymbolScopeResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(spec, status="failed", reason="descriptor_build_failed")
            descriptor["error"] = str(exc)
            return BundlerSymbolScopeResult(status="failed", descriptor=descriptor, side_effect_policy=policy, error=str(exc), reason="descriptor_build_failed")

    def _descriptor(self, spec: BundlerSymbolScopeSpec) -> dict[str, Any]:
        assert spec.source_map is not None
        summary = self._source_map_summary(spec.source_map, spec.source_map_fetch_result)
        classification = self._classify_bundler(spec)
        source_match = self._source_match(spec)
        source_location = self._source_location(spec)
        name_metadata = self._name_metadata(spec)
        scope_candidates = self._scope_candidates(spec, source_location)
        blockers = self._blockers(spec, source_match, name_metadata, scope_candidates)
        status = "blocked" if blockers and not scope_candidates else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.bundler-symbol-scope.v1",
            "status": status,
            "review_only": True,
            "reason": blockers[0] if status == "blocked" else None,
            "symbol_request": {
                "symbol_name": spec.symbol_name,
                "original_source": spec.original_source,
                "original_line_number": spec.original_line_number,
                "original_column_number": spec.original_column_number,
                "source_map_bias": spec.source_map_bias,
                "script_url": spec.script_url,
                "script_url_redacted": _redact_url(spec.script_url) if spec.script_url else "",
            },
            "source_map_summary": summary,
            "bundler_classification": classification,
            "source_match": source_match,
            "generated_location": source_location.to_dict() if source_location else {},
            "name_metadata": name_metadata,
            "scope_candidates": scope_candidates,
            "scope_candidate_count": len(scope_candidates),
            "hook_readiness": {
                "source_logpoint_reviewable": bool(scope_candidates or source_location),
                "source_logpoint_requires_review": bool(scope_candidates or source_location),
                "function_hook_requires_runtime_candidate": True,
                "module_hook_requires_module_candidate": True,
                "automatic_logpoint_install_supported": False,
                "automatic_function_hook_supported": False,
                "automatic_module_hook_supported": False,
            },
            "blockers": blockers,
            "next_action": "review_symbol_scope_before_source_logpoint_or_hook" if status == "ready_for_review" else "provide_source_map_symbol_and_original_source",
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, spec: BundlerSymbolScopeSpec, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.bundler-symbol-scope.v1",
            "status": status,
            "review_only": True,
            "reason": reason,
            "symbol_request": {
                "symbol_name": spec.symbol_name,
                "original_source": spec.original_source,
                "script_url": spec.script_url,
                "script_url_redacted": _redact_url(spec.script_url) if spec.script_url else "",
            },
            "source_map_summary": self._source_map_summary(spec.source_map or {}, spec.source_map_fetch_result),
            "bundler_classification": self._classify_bundler(spec),
            "source_match": {"matched": False, "reason": reason},
            "generated_location": {},
            "name_metadata": {"requested_symbol": spec.symbol_name, "name_present": False, "mapping_name_match_count": 0},
            "scope_candidates": [],
            "scope_candidate_count": 0,
            "hook_readiness": {
                "source_logpoint_reviewable": False,
                "source_logpoint_requires_review": False,
                "function_hook_requires_runtime_candidate": True,
                "module_hook_requires_module_candidate": True,
                "automatic_logpoint_install_supported": False,
                "automatic_function_hook_supported": False,
                "automatic_module_hook_supported": False,
            },
            "blockers": [reason],
            "next_action": "provide_source_map_payload",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _source_map_summary(cls, source_map: dict[str, Any], fetch_result: dict[str, Any]) -> dict[str, Any]:
        sources = source_map.get("sources") if isinstance(source_map.get("sources"), list) else []
        names = source_map.get("names") if isinstance(source_map.get("names"), list) else []
        sections = source_map.get("sections") if isinstance(source_map.get("sections"), list) else []
        return {
            "version": source_map.get("version") or fetch_result.get("version"),
            "sources_count": len(sources) or int(fetch_result.get("sources_count") or 0),
            "names_count": len(names) or int(fetch_result.get("names_count") or 0),
            "section_count": len(sections) or int(fetch_result.get("section_count") or 0),
            "sourceRoot": source_map.get("sourceRoot") or "",
            "indexed_section_depth": cls._indexed_depth(source_map),
            "source_map_fetch_metadata_present": bool(fetch_result),
            "source_map_payload_present": bool(source_map),
        }

    @classmethod
    def _indexed_depth(cls, source_map: dict[str, Any]) -> int:
        sections = source_map.get("sections")
        if not isinstance(sections, list):
            return 0
        depths = [1]
        for section in sections:
            if isinstance(section, dict) and isinstance(section.get("map"), dict):
                depths.append(1 + cls._indexed_depth(section["map"]))
        return max(depths)

    def _classify_bundler(self, spec: BundlerSymbolScopeSpec) -> dict[str, Any]:
        signals: list[str] = []
        haystacks = [spec.script_url, spec.script_source]
        if isinstance(spec.source_map, dict):
            haystacks.extend(str(item) for item in spec.source_map.get("sources", []) if item is not None)
            haystacks.append(str(spec.source_map.get("sourceRoot") or ""))
        for item in spec.script_inventory:
            haystacks.extend(str(item.get(key) or "") for key in ("url", "source_url", "sourceUrl", "sourceRoot"))
        joined = "\n".join(haystacks).lower()
        candidates = [
            ("webpack", ("webpack://", "__webpack_require__", "webpackchunk", "webpackjsonp", "webpackbootstrap")),
            ("vite", ("/@vite/", "vite/client", "import.meta.hot", "__vite", "node_modules/.vite")),
            ("rollup", ("rollup", "system.register", "__chunk", "generated by rollup")),
            ("esbuild", ("esbuild", "__defprop", "__export", "__toesm", "__commonjs")),
            ("parcel", ("parcelrequire", "parcel", "node_modules/.parcel-cache")),
        ]
        for bundler, needles in candidates:
            matched = [needle for needle in needles if needle in joined]
            if matched:
                signals.extend(f"{bundler}:{needle}" for needle in matched[:4])
                return {"bundler_kind": bundler, "confidence": "high" if len(matched) > 1 else "medium", "signals": signals}
        return {"bundler_kind": "unknown", "confidence": "low", "signals": []}

    def _source_match(self, spec: BundlerSymbolScopeSpec) -> dict[str, Any]:
        if not spec.original_source or not isinstance(spec.source_map, dict):
            return {"matched": False, "reason": "original_source_not_provided"}
        match = self._find_source_match(spec.source_map, spec.original_source)
        return match or {"matched": False, "requested_source": spec.original_source}

    def _source_location(self, spec: BundlerSymbolScopeSpec) -> GeneratedLocation | None:
        if not isinstance(spec.source_map, dict) or not spec.original_source or spec.original_line_number is None:
            return None
        return SourceMapRemapper.location_from_source_map(
            spec.source_map,
            original_source=spec.original_source,
            original_line_number=spec.original_line_number,
            original_column_number=spec.original_column_number,
            bias=spec.source_map_bias,
        )

    def _name_metadata(self, spec: BundlerSymbolScopeSpec) -> dict[str, Any]:
        names = self._names(spec.source_map or {})
        requested = spec.symbol_name
        name_indices = [index for index, item in enumerate(names) if item == requested] if requested else []
        mapping_match_count = sum(1 for mapping in self._iter_scoped_mappings(spec.source_map or {}) if mapping.get("name") == requested) if requested else 0
        return {
            "requested_symbol": requested,
            "names_count": len(names),
            "name_present": bool(name_indices),
            "name_indices": name_indices,
            "name_index": name_indices[0] if name_indices else None,
            "mapping_name_match_count": mapping_match_count,
        }

    def _scope_candidates(self, spec: BundlerSymbolScopeSpec, source_location: GeneratedLocation | None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        if source_location is not None:
            entry = {
                "kind": "source-map-original-location",
                "symbol_name": spec.symbol_name,
                "original_source": source_location.source or spec.original_source,
                "original_line_number": source_location.original_line_number,
                "original_column_number": source_location.original_column_number,
                "generated_line_number": source_location.line_number,
                "generated_column_number": source_location.column_number,
                "strategy": source_location.strategy,
                "metadata": source_location.metadata,
            }
            candidates.append(entry)
            seen.add((entry["generated_line_number"], entry["generated_column_number"], entry["original_source"]))
        if spec.symbol_name:
            for mapping in self._iter_scoped_mappings(spec.source_map or {}):
                if mapping.get("name") != spec.symbol_name:
                    continue
                resolved_source = str(mapping.get("source") or "")
                if spec.original_source and not self._source_matches(resolved_source, spec.original_source):
                    continue
                entry = {
                    "kind": "source-map-name",
                    "symbol_name": spec.symbol_name,
                    "original_source": resolved_source,
                    "original_line_number": mapping.get("original_line_number"),
                    "original_column_number": mapping.get("original_column_number"),
                    "generated_line_number": mapping.get("generated_line_number"),
                    "generated_column_number": mapping.get("generated_column_number"),
                    "strategy": "source_map_name",
                    "metadata": {
                        "source_index": mapping.get("source_index"),
                        "name_index": mapping.get("name_index"),
                        "section_stack": mapping.get("section_stack", []),
                        "indexed_section_depth": len(mapping.get("section_stack", [])) if isinstance(mapping.get("section_stack"), list) else 0,
                    },
                }
                key = (entry["generated_line_number"], entry["generated_column_number"], entry["original_source"])
                if key in seen:
                    continue
                candidates.append(entry)
                seen.add(key)
        return candidates[:20]

    @staticmethod
    def _blockers(spec: BundlerSymbolScopeSpec, source_match: dict[str, Any], name_metadata: dict[str, Any], scope_candidates: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        if not spec.symbol_name and not spec.original_source:
            blockers.append("missing_symbol_or_original_source")
        if spec.original_source and not source_match.get("matched"):
            blockers.append("original_source_not_found_in_source_map")
        if spec.symbol_name and not name_metadata.get("name_present"):
            blockers.append("symbol_name_not_present_in_source_map_names")
        if (spec.symbol_name or spec.original_source) and not scope_candidates:
            blockers.append("no_generated_scope_candidate")
        return blockers

    def _find_source_match(self, source_map: dict[str, Any], original_source: str) -> dict[str, Any] | None:
        sources = source_map.get("sources") if isinstance(source_map.get("sources"), list) else []
        if sources:
            index, _resolved, match = SourceMapRemapper._find_source_index(sources, original_source=original_source, source_root=str(source_map.get("sourceRoot") or ""))
            if index >= 0:
                match = dict(match)
                match["matched"] = True
                match["source_index"] = index
                return match
        sections = source_map.get("sections")
        if isinstance(sections, list):
            for section_index, section in enumerate(sections):
                if isinstance(section, dict) and isinstance(section.get("map"), dict):
                    nested = self._find_source_match(section["map"], original_source)
                    if nested:
                        nested = dict(nested)
                        nested["section_index"] = section_index
                        return nested
        return None

    def _iter_scoped_mappings(
        self,
        source_map: dict[str, Any],
        *,
        base_line: int = 0,
        base_column: int = 0,
        section_stack: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        section_stack = section_stack or []
        sections = source_map.get("sections")
        if isinstance(sections, list):
            collected: list[dict[str, Any]] = []
            for index, section in enumerate(sections):
                if not isinstance(section, dict) or not isinstance(section.get("map"), dict):
                    continue
                offset = section.get("offset") if isinstance(section.get("offset"), dict) else {}
                offset_line = int(offset.get("line", 0) or 0)
                offset_column = int(offset.get("column", 0) or 0)
                entry = {"section_index": index, "offset_line": offset_line, "offset_column": offset_column}
                collected.extend(
                    self._iter_scoped_mappings(
                        section["map"],
                        base_line=base_line + offset_line,
                        base_column=base_column + offset_column,
                        section_stack=[*section_stack, entry],
                    )
                )
            return collected
        sources = source_map.get("sources") if isinstance(source_map.get("sources"), list) else []
        names = self._names(source_map)
        scoped: list[dict[str, Any]] = []
        for mapping in SourceMapRemapper.iter_mappings(source_map):
            item = dict(mapping)
            generated_line = int(item.get("generated_line_number", 0)) + base_line
            generated_column = int(item.get("generated_column_number", 0)) + (base_column if int(item.get("generated_line_number", 0)) == 0 else 0)
            item["generated_line_number"] = generated_line
            item["generated_column_number"] = generated_column
            source_index = item.get("source_index")
            if isinstance(source_index, int) and 0 <= source_index < len(sources):
                item["source"] = SourceMapRemapper._join_source_root(str(source_map.get("sourceRoot") or ""), str(sources[source_index]))
            name_index = item.get("name_index")
            if isinstance(name_index, int) and 0 <= name_index < len(names):
                item["name"] = names[name_index]
            item["section_stack"] = list(section_stack)
            scoped.append(item)
        return scoped

    @staticmethod
    def _names(source_map: dict[str, Any]) -> list[str]:
        names = source_map.get("names") if isinstance(source_map.get("names"), list) else []
        return [str(item) for item in names]

    @staticmethod
    def _source_matches(candidate: str, requested: str) -> bool:
        return bool(SourceMapRemapper._source_candidates(candidate).intersection(SourceMapRemapper._source_candidates(requested)))

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapHookCandidateRefinementSpec:
    """Review-only Source Map hook candidate refinement request.

    The descriptor consumes already-reviewed Source Map symbol-scope metadata
    and optional module-discovery hints. It never starts a browser, evaluates
    JavaScript, sends CDP commands, installs hooks, fetches Source Maps, exports
    raw source content, calls MCP, or touches mobile runtime chains.
    """

    bundler_symbol_scope: dict[str, Any] = field(default_factory=dict)
    source_map_consumer_materialization: dict[str, Any] = field(default_factory=dict)
    source_map_typed_payload_preflight: dict[str, Any] = field(default_factory=dict)
    module_discovery: dict[str, Any] = field(default_factory=dict)
    module_candidates: list[dict[str, Any]] = field(default_factory=list)
    function_paths: tuple[str, ...] = ()
    requested_symbol: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapHookCandidateRefinementSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_hook_candidates",
                "sourceMapHookCandidates",
                "source_map_hook_candidate_refinement",
                "sourceMapHookCandidateRefinement",
                "source_map_hook_candidate_review",
                "sourceMapHookCandidateReview",
                "refine_source_map_hook_candidates",
                "refineSourceMapHookCandidates",
            )
        )
        symbol_scope = cls._object_alias(
            context,
            "bundler_symbol_scope",
            "bundler-symbol-scope",
            "bundlerSymbolScope",
            "source_map_symbol_scope",
            "sourceMapSymbolScope",
        )
        materialization = cls._object_alias(
            context,
            "source_map_consumer_materialization",
            "source-map-consumer-materialization",
            "sourceMapConsumerMaterialization",
        )
        preflight = cls._object_alias(
            context,
            "source_map_typed_payload_preflight",
            "source-map-typed-payload-preflight",
            "sourceMapTypedPayloadPreflight",
            "source_map_consumer_typed_payload_preflight",
            "sourceMapConsumerTypedPayloadPreflight",
        )
        module_discovery = cls._object_alias(context, "module_discovery", "module-discovery", "moduleDiscovery")
        module_candidates = cls._dict_list_alias(context, "module_candidates", "moduleCandidates", "modules")
        if not module_candidates and isinstance(module_discovery.get("modules"), list):
            module_candidates = [item for item in module_discovery["modules"] if isinstance(item, dict)]
        if not requested and not any((symbol_scope, materialization, preflight, module_candidates)):
            return None
        return cls(
            bundler_symbol_scope=symbol_scope,
            source_map_consumer_materialization=materialization,
            source_map_typed_payload_preflight=preflight,
            module_discovery=module_discovery,
            module_candidates=module_candidates,
            function_paths=cls._string_tuple_alias(context.get("function_paths", context.get("functionPaths", context.get("runtime_function_paths", context.get("runtimeFunctionPaths"))))),
            requested_symbol=str(context.get("symbol_name", context.get("symbolName", context.get("function_name", context.get("functionName", "")))) or ""),
        )

    @classmethod
    def _object_alias(cls, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {}

    @staticmethod
    def _dict_list_alias(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    continue
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _string_tuple_alias(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            raw_items = [item.strip() for item in value.replace(";", ",").split(",")]
        elif isinstance(value, (list, tuple, set)):
            raw_items = [str(item).strip() for item in value]
        else:
            raw_items = []
        items: list[str] = []
        for item in raw_items:
            if item and item not in items:
                items.append(item)
        return tuple(items)


@dataclass(slots=True)
class SourceMapHookCandidateRefinementResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapHookCandidateRefinementManager:
    """Refine reviewed Source Map symbol-scope evidence into hook candidates."""

    def review(self, spec: SourceMapHookCandidateRefinementSpec | None) -> SourceMapHookCandidateRefinementResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapHookCandidateRefinementResult(status="unsupported", reason="missing_source_map_hook_candidate_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapHookCandidateRefinementResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_hook_candidate_refinement_failed")
            descriptor["error"] = str(exc)
            return SourceMapHookCandidateRefinementResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_hook_candidate_refinement_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapHookCandidateRefinementSpec) -> dict[str, Any]:
        source_status = self._source_status(spec)
        blockers = self._input_blockers(spec, source_status)
        candidates = [] if blockers else self._candidates(spec, source_status)
        if not candidates and not blockers:
            blockers.append("source_map_hook_candidate_refinement_no_candidates")
        warnings = self._warnings(spec, candidates)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-hook-candidates.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "candidate_refinement_only": True,
            "source_status": source_status,
            "requested_symbol": spec.requested_symbol or source_status.get("symbol_name", ""),
            "bundler_kind": source_status.get("bundler_kind", "unknown"),
            "source_scope_candidate_count": source_status.get("scope_candidate_count", 0),
            "module_candidate_count": len(spec.module_candidates),
            "function_path_count": len(spec.function_paths),
            "candidate_count": len(candidates),
            "ready_for_hook_install_review_count": sum(1 for item in candidates if item.get("ready_for_hook_install_review")),
            "candidates": candidates,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, candidates),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-hook-candidates.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "candidate_refinement_only": True,
            "reason": reason,
            "source_status": {},
            "requested_symbol": "",
            "bundler_kind": "unknown",
            "source_scope_candidate_count": 0,
            "module_candidate_count": 0,
            "function_path_count": 0,
            "candidate_count": 0,
            "ready_for_hook_install_review_count": 0,
            "candidates": [],
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_bundler_symbol_scope_for_hook_candidate_refinement",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _source_status(cls, spec: SourceMapHookCandidateRefinementSpec) -> dict[str, Any]:
        symbol_scope = spec.bundler_symbol_scope
        request = symbol_scope.get("symbol_request") if isinstance(symbol_scope.get("symbol_request"), dict) else {}
        classification = symbol_scope.get("bundler_classification") if isinstance(symbol_scope.get("bundler_classification"), dict) else {}
        hook_readiness = symbol_scope.get("hook_readiness") if isinstance(symbol_scope.get("hook_readiness"), dict) else {}
        scope_candidates = symbol_scope.get("scope_candidates") if isinstance(symbol_scope.get("scope_candidates"), list) else []
        typed_hook_payload_ready = cls._typed_hook_payload_ready(spec)
        return {
            "bundler_symbol_scope_present": bool(symbol_scope),
            "bundler_symbol_scope_status": cls._status(symbol_scope),
            "symbol_name": spec.requested_symbol or str(request.get("symbol_name") or ""),
            "original_source": str(request.get("original_source") or ""),
            "bundler_kind": classification.get("bundler_kind") or "unknown",
            "scope_candidate_count": len([item for item in scope_candidates if isinstance(item, dict)]),
            "source_logpoint_reviewable": bool(hook_readiness.get("source_logpoint_reviewable")),
            "function_hook_requires_runtime_candidate": bool(hook_readiness.get("function_hook_requires_runtime_candidate", True)),
            "module_hook_requires_module_candidate": bool(hook_readiness.get("module_hook_requires_module_candidate", True)),
            "typed_hook_payload_ready": typed_hook_payload_ready,
            "materialization_status": cls._status(spec.source_map_consumer_materialization),
            "typed_payload_preflight_status": cls._status(spec.source_map_typed_payload_preflight),
        }

    @classmethod
    def _typed_hook_payload_ready(cls, spec: SourceMapHookCandidateRefinementSpec) -> bool:
        payloads: list[dict[str, Any]] = []
        raw_materialized = spec.source_map_consumer_materialization.get("typed_review_payloads")
        if isinstance(raw_materialized, list):
            payloads.extend(item for item in raw_materialized if isinstance(item, dict))
        raw_preflight = spec.source_map_typed_payload_preflight.get("preflight_payloads")
        if isinstance(raw_preflight, list):
            payloads.extend(item for item in raw_preflight if isinstance(item, dict))
        for payload in payloads:
            if payload.get("consumer") == "hook" and cls._status(payload) in {"ready_for_review", "ready"}:
                return True
        return False

    @classmethod
    def _input_blockers(cls, spec: SourceMapHookCandidateRefinementSpec, source_status: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not source_status["bundler_symbol_scope_present"]:
            blockers.append("bundler_symbol_scope_descriptor_missing")
        elif source_status["bundler_symbol_scope_status"] in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("bundler_symbol_scope_not_ready")
        if source_status["scope_candidate_count"] <= 0:
            blockers.append("bundler_symbol_scope_has_no_scope_candidates")
        for label, payload in (
            ("bundler_symbol_scope", spec.bundler_symbol_scope),
            ("source_map_consumer_materialization", spec.source_map_consumer_materialization),
            ("source_map_typed_payload_preflight", spec.source_map_typed_payload_preflight),
        ):
            policy = payload.get("side_effect_policy") if isinstance(payload.get("side_effect_policy"), dict) else {}
            blockers.extend(cls._side_effect_blockers(policy, prefix=label))
        return blockers

    @classmethod
    def _candidates(cls, spec: SourceMapHookCandidateRefinementSpec, source_status: dict[str, Any]) -> list[dict[str, Any]]:
        symbol_scope = spec.bundler_symbol_scope
        scope_candidates = [item for item in symbol_scope.get("scope_candidates", []) if isinstance(item, dict)]
        function_paths = list(spec.function_paths)
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, scope_candidate in enumerate(scope_candidates):
            symbol = str(scope_candidate.get("symbol_name") or source_status.get("symbol_name") or "").strip()
            if not symbol:
                continue
            candidate_id = cls._candidate_id("function", symbol, scope_candidate, index)
            ready = bool(function_paths)
            candidate = {
                "candidate_id": candidate_id,
                "candidate_kind": "source-map-function-symbol",
                "hook_kind": "function",
                "status": "ready_for_review",
                "review_required": True,
                "install_automatically": False,
                "ready_for_hook_install_review": ready,
                "confidence": cls._confidence(symbol, scope_candidate, source_status, ready),
                "symbol_name": symbol,
                "original_source": scope_candidate.get("original_source") or source_status.get("original_source") or "",
                "generated_location": {
                    "line_number": scope_candidate.get("generated_line_number"),
                    "column_number": scope_candidate.get("generated_column_number"),
                    "strategy": scope_candidate.get("strategy") or "",
                },
                "source_scope_candidate": scope_candidate,
                "review_blockers": [] if ready else ["runtime_function_path_required_before_install_review"],
                "suggested_hook_install_input": {
                    "hook_kind": "function",
                    "function_name": symbol,
                    "function_paths": function_paths,
                    "candidate_id": candidate_id,
                    "cdp_command": None,
                    "install_supported_now": False,
                    "requires_explicit_review": True,
                },
                "next_action": "review_source_map_function_hook_install_input" if ready else "add_runtime_function_path_before_hook_install_review",
            }
            if candidate_id not in seen:
                candidates.append(candidate)
                seen.add(candidate_id)
        for module_candidate in spec.module_candidates:
            for candidate in cls._module_candidates(module_candidate, source_status):
                if candidate["candidate_id"] in seen:
                    continue
                candidates.append(candidate)
                seen.add(candidate["candidate_id"])
        return candidates[:20]

    @classmethod
    def _module_candidates(cls, module_candidate: dict[str, Any], source_status: dict[str, Any]) -> list[dict[str, Any]]:
        symbol = str(source_status.get("symbol_name") or "").strip()
        export_names = cls._string_list(module_candidate.get("export_names", module_candidate.get("exportNames", [])))
        explicit_export = str(module_candidate.get("export_name", module_candidate.get("exportName", "")) or "").strip()
        if explicit_export and explicit_export not in export_names:
            export_names.append(explicit_export)
        if symbol:
            export_names = [item for item in export_names if item == symbol or item.endswith(f".{symbol}")]
        module_id = str(module_candidate.get("module_id", module_candidate.get("moduleId", module_candidate.get("id", ""))) or "").strip()
        runtime_path = str(module_candidate.get("runtime_path", module_candidate.get("runtimePath", module_candidate.get("require_path", module_candidate.get("requirePath", "")))) or "").strip()
        if not module_id or not runtime_path or not export_names:
            return []
        candidates: list[dict[str, Any]] = []
        for export_name in export_names:
            candidate_id = f"source-map-hook-module:{module_id}:{export_name}"
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_kind": "source-map-module-export",
                    "hook_kind": "module",
                    "status": "ready_for_review",
                    "review_required": True,
                    "install_automatically": False,
                    "ready_for_hook_install_review": True,
                    "confidence": {"label": "high" if symbol and export_name == symbol else "medium", "score": 0.8 if symbol and export_name == symbol else 0.65},
                    "symbol_name": symbol or export_name,
                    "module_id": module_id,
                    "export_name": export_name,
                    "runtime_path": runtime_path,
                    "source_module_candidate": module_candidate,
                    "review_blockers": [],
                    "suggested_hook_install_input": {
                        "hook_kind": "module",
                        "module_id": module_id,
                        "export_name": export_name,
                        "require_path": runtime_path,
                        "candidate_id": candidate_id,
                        "cdp_command": None,
                        "install_supported_now": False,
                        "requires_explicit_review": True,
                    },
                    "next_action": "review_source_map_module_hook_install_input",
                }
            )
        return candidates

    @staticmethod
    def _candidate_id(kind: str, symbol: str, scope_candidate: dict[str, Any], index: int) -> str:
        line = scope_candidate.get("generated_line_number", "x")
        column = scope_candidate.get("generated_column_number", "x")
        safe_symbol = re.sub(r"[^A-Za-z0-9_.:$-]+", "_", symbol)[:80] or "anonymous"
        return f"source-map-hook-{kind}:{safe_symbol}:{line}:{column}:{index}"

    @staticmethod
    def _confidence(symbol: str, scope_candidate: dict[str, Any], source_status: dict[str, Any], ready: bool) -> dict[str, Any]:
        score = 0.45
        signals: list[str] = []
        if symbol:
            score += 0.15
            signals.append("symbol_name_present")
        if scope_candidate.get("strategy") in {"source_map_name", "source_map_generated_exact"}:
            score += 0.15
            signals.append(str(scope_candidate.get("strategy")))
        if source_status.get("typed_hook_payload_ready"):
            score += 0.1
            signals.append("typed_hook_payload_ready")
        if ready:
            score += 0.15
            signals.append("runtime_function_path_available")
        score = min(score, 0.95)
        label = "high" if score >= 0.8 else "medium" if score >= 0.55 else "low"
        return {"score": round(score, 2), "label": label, "signals": signals}

    @staticmethod
    def _warnings(spec: SourceMapHookCandidateRefinementSpec, candidates: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = ["source_map_hook_candidates_require_explicit_review_before_install"]
        if candidates and not any(item.get("ready_for_hook_install_review") for item in candidates):
            warnings.append("runtime_hook_install_inputs_still_required")
        if not spec.module_candidates:
            warnings.append("module_discovery_candidates_not_attached")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], candidates: list[dict[str, Any]]) -> str:
        if "bundler_symbol_scope_descriptor_missing" in blockers or "bundler_symbol_scope_not_ready" in blockers:
            return "provide_ready_bundler_symbol_scope_for_hook_candidate_refinement"
        if "bundler_symbol_scope_has_no_scope_candidates" in blockers:
            return "rerun_bundler_symbol_scope_with_symbol_or_original_source"
        if blockers:
            return "fix_source_map_hook_candidate_refinement_inputs"
        if any(item.get("ready_for_hook_install_review") for item in candidates):
            return "review_source_map_hook_candidates_before_selected_hook_install"
        return "add_runtime_function_or_module_candidates_before_hook_install_review"

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _string_list(payload: Any) -> list[str]:
        if isinstance(payload, str):
            return [item.strip() for item in payload.replace(";", ",").split(",") if item.strip()]
        if isinstance(payload, (list, tuple, set)):
            return [str(item).strip() for item in payload if str(item).strip()]
        return []

    @staticmethod
    def _side_effect_blockers(policy: dict[str, Any], *, prefix: str) -> list[str]:
        blockers: list[str] = []
        for key in (
            "raw_source_content_exported",
            "preview_exported",
            "fetch_source_map",
            "browser_started",
            "cdp_command_sent",
            "runtime_evaluated",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "calls_mcp",
            "mobile_runtime_used",
        ):
            if policy.get(key):
                blockers.append(f"{prefix}_{key}_detected")
        return blockers

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "candidate_refinement_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "automatic_hook_installation": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapHookCandidateSelectionSpec:
    """Review-only handoff from Source Map hook candidates to selected executor input review."""

    source_map_hook_candidates: dict[str, Any] = field(default_factory=dict)
    selected_candidate_id: str = ""
    selected_candidate_index: int | None = None
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapHookCandidateSelectionSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_hook_candidate_selection",
                "sourceMapHookCandidateSelection",
                "source_map_hook_candidate_handoff",
                "sourceMapHookCandidateHandoff",
                "select_source_map_hook_candidate",
                "selectSourceMapHookCandidate",
                "source_map_hook_candidate_executor_input",
                "sourceMapHookCandidateExecutorInput",
            )
        )
        candidates = SourceMapHookCandidateRefinementSpec._object_alias(
            context,
            "source_map_hook_candidates",
            "source-map-hook-candidates",
            "sourceMapHookCandidates",
            "source_map_hook_candidate_refinement",
            "sourceMapHookCandidateRefinement",
            "source_map_hook_candidate_review",
            "sourceMapHookCandidateReview",
        )
        selected_index = cls._optional_int(context.get("selected_candidate_index", context.get("selectedCandidateIndex", context.get("candidate_index", context.get("candidateIndex")))))
        selected_id = str(context.get("selected_candidate_id", context.get("selectedCandidateId", context.get("candidate_id", context.get("candidateId", "")))) or "")
        if not requested and not candidates and not selected_id and selected_index is None:
            return None
        return cls(
            source_map_hook_candidates=candidates,
            selected_candidate_id=selected_id,
            selected_candidate_index=selected_index,
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


@dataclass(slots=True)
class SourceMapHookCandidateSelectionResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapHookCandidateSelectionManager:
    """Select one reviewed hook candidate and build downstream review input."""

    def review(self, spec: SourceMapHookCandidateSelectionSpec | None) -> SourceMapHookCandidateSelectionResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapHookCandidateSelectionResult(status="unsupported", reason="missing_source_map_hook_candidate_selection_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapHookCandidateSelectionResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_hook_candidate_selection_failed")
            descriptor["error"] = str(exc)
            return SourceMapHookCandidateSelectionResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_hook_candidate_selection_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapHookCandidateSelectionSpec) -> dict[str, Any]:
        candidates_payload = spec.source_map_hook_candidates
        candidates = [item for item in candidates_payload.get("candidates", []) if isinstance(item, dict)] if isinstance(candidates_payload.get("candidates"), list) else []
        blockers = self._input_blockers(candidates_payload, candidates, spec)
        selected_index, selected_candidate = self._select_candidate(candidates, spec, blockers)
        selected_executor_input = {} if blockers or not selected_candidate else self._selected_executor_input(selected_candidate, candidates_payload)
        selected_review = {} if blockers or not selected_executor_input else self._selected_review(selected_candidate, selected_executor_input, spec)
        review_context = {} if blockers or not selected_review else self._selected_executor_input_review_context(selected_review, selected_executor_input, spec)
        if selected_executor_input:
            blockers.extend(SourceMapSelectedExecutorInputReviewManager._consumer_executor_input_blockers("hook", selected_executor_input))
        warnings = self._warnings(selected_candidate)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-hook-candidate-selection.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "source_candidates_schema_version": str(candidates_payload.get("schema_version") or ""),
            "source_candidates_status": self._status(candidates_payload),
            "candidate_count": len(candidates),
            "ready_for_hook_install_review_count": sum(1 for item in candidates if item.get("ready_for_hook_install_review")),
            "selected_candidate_id": str(selected_candidate.get("candidate_id") or "") if selected_candidate else "",
            "selected_candidate_index": selected_index,
            "selected_candidate": selected_candidate or {},
            "selected_action_id": str(selected_review.get("action_id") or ""),
            "selected_consumer": "hook" if selected_review else "",
            "selected_followthrough_review_surface": str(selected_review.get("followthrough_review_surface") or ""),
            "selected_review": selected_review,
            "selected_executor_input": selected_executor_input,
            "source_map_selected_executor_input_review_context": review_context,
            "ready_for_selected_executor_input_review": bool(review_context) and not blockers,
            "reviewer": spec.reviewer,
            "hook_installed": False,
            "automatic_hook_installation": False,
            "runtime_evaluated": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-hook-candidate-selection.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_candidates_schema_version": "",
            "source_candidates_status": "",
            "candidate_count": 0,
            "ready_for_hook_install_review_count": 0,
            "selected_candidate_id": "",
            "selected_candidate_index": None,
            "selected_candidate": {},
            "selected_action_id": "",
            "selected_consumer": "",
            "selected_followthrough_review_surface": "",
            "selected_review": {},
            "selected_executor_input": {},
            "source_map_selected_executor_input_review_context": {},
            "ready_for_selected_executor_input_review": False,
            "reviewer": "",
            "hook_installed": False,
            "automatic_hook_installation": False,
            "runtime_evaluated": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_hook_candidates_for_selection",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, payload: dict[str, Any], candidates: list[dict[str, Any]], spec: SourceMapHookCandidateSelectionSpec) -> list[str]:
        blockers: list[str] = []
        if not payload:
            blockers.append("source_map_hook_candidates_missing")
        elif payload.get("schema_version") not in {None, "", "reverse-deepagent.source-map-hook-candidates.v1"}:
            blockers.append("source_map_hook_candidates_schema_mismatch")
        status = cls._status(payload)
        if status in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_hook_candidates_not_ready")
        if not candidates:
            blockers.append("source_map_hook_candidates_empty")
        if len(candidates) > 1 and not spec.selected_candidate_id and spec.selected_candidate_index is None:
            blockers.append("source_map_hook_candidate_selection_ambiguous")
        policy = payload.get("side_effect_policy") if isinstance(payload.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_hook_candidates"))
        if payload.get("hook_installed") is True or payload.get("automatic_hook_installation") is True:
            blockers.append("source_map_hook_candidates_unexpected_installation")
        return blockers

    @classmethod
    def _select_candidate(
        cls,
        candidates: list[dict[str, Any]],
        spec: SourceMapHookCandidateSelectionSpec,
        blockers: list[str],
    ) -> tuple[int | None, dict[str, Any]]:
        if not candidates:
            return None, {}
        selected_index: int | None = None
        selected: dict[str, Any] = {}
        if spec.selected_candidate_id:
            for index, candidate in enumerate(candidates):
                if str(candidate.get("candidate_id") or "") == spec.selected_candidate_id:
                    selected_index = index
                    selected = candidate
                    break
            if not selected:
                blockers.append("source_map_hook_selected_candidate_id_not_found")
                return None, {}
        elif spec.selected_candidate_index is not None:
            if spec.selected_candidate_index < 0 or spec.selected_candidate_index >= len(candidates):
                blockers.append("source_map_hook_selected_candidate_index_out_of_range")
                return None, {}
            selected_index = spec.selected_candidate_index
            selected = candidates[selected_index]
        elif len(candidates) == 1:
            selected_index = 0
            selected = candidates[0]
        else:
            return None, {}
        if selected.get("ready_for_hook_install_review") is not True:
            blockers.append("source_map_hook_selected_candidate_not_ready_for_install_review")
        if selected.get("install_automatically") is True:
            blockers.append("source_map_hook_selected_candidate_auto_install_claim_detected")
        if selected.get("hook_installed") is True:
            blockers.append("source_map_hook_selected_candidate_already_installed_claim_detected")
        return selected_index, selected

    @staticmethod
    def _selected_executor_input(candidate: dict[str, Any], source_payload: dict[str, Any]) -> dict[str, Any]:
        suggested = candidate.get("suggested_hook_install_input") if isinstance(candidate.get("suggested_hook_install_input"), dict) else {}
        source_status = source_payload.get("source_status") if isinstance(source_payload.get("source_status"), dict) else {}
        hook_symbol_scope = {
            "candidate_id": candidate.get("candidate_id") or "",
            "candidate_kind": candidate.get("candidate_kind") or "",
            "hook_kind": candidate.get("hook_kind") or suggested.get("hook_kind") or "",
            "symbol_name": candidate.get("symbol_name") or source_status.get("symbol_name") or "",
            "bundler_kind": source_payload.get("bundler_kind") or source_status.get("bundler_kind") or "unknown",
            "original_source": candidate.get("original_source") or source_status.get("original_source") or "",
            "confidence": candidate.get("confidence") if isinstance(candidate.get("confidence"), dict) else {},
            "source_map_hook_candidate_id": candidate.get("candidate_id") or "",
            "hook_installed": False,
        }
        if candidate.get("generated_location") is not None:
            hook_symbol_scope["generated_location"] = candidate.get("generated_location")
        if candidate.get("module_id") is not None:
            hook_symbol_scope["module_id"] = candidate.get("module_id")
        if candidate.get("export_name") is not None:
            hook_symbol_scope["export_name"] = candidate.get("export_name")
        if candidate.get("runtime_path") is not None:
            hook_symbol_scope["runtime_path"] = candidate.get("runtime_path")
        hook_install_input = dict(suggested)
        hook_install_input.setdefault("candidate_id", candidate.get("candidate_id") or "")
        hook_install_input.setdefault("requires_explicit_review", True)
        hook_install_input.setdefault("install_supported_now", False)
        hook_install_input.setdefault("cdp_command", None)
        return {
            "hook_symbol_scope": hook_symbol_scope,
            "hook_candidate_review_required": True,
            "hook_install_supported_now": False,
            "hook_install_input": hook_install_input,
            "source_map_hook_candidate_id": candidate.get("candidate_id") or "",
            "cdp_command": None,
            "requires_review_before_hook_install": True,
        }

    @staticmethod
    def _selected_review(candidate: dict[str, Any], selected_executor_input: dict[str, Any], spec: SourceMapHookCandidateSelectionSpec) -> dict[str, Any]:
        candidate_id = str(candidate.get("candidate_id") or "")
        action_id = f"source-map-hook-candidate:{candidate_id}"
        return {
            "status": "ready_for_review",
            "action_id": action_id,
            "consumer": "hook",
            "followthrough_review_surface": "review_hook_symbol_scope_executor_input",
            "review_required": True,
            "explicit_review_required": True,
            "execute_automatically": False,
            "executor_invoked": False,
            "executor_input": selected_executor_input,
            "review_prompt": "Review selected Source Map hook candidate before any runtime hook installation.",
            "next_action": "review_selected_source_map_hook_candidate_input",
            "reviewer": spec.reviewer,
            "source_candidate_id": candidate_id,
            "side_effect_policy": SourceMapHookCandidateSelectionManager._side_effect_policy(),
        }

    @staticmethod
    def _selected_executor_input_review_context(selected_review: dict[str, Any], selected_executor_input: dict[str, Any], spec: SourceMapHookCandidateSelectionSpec) -> dict[str, Any]:
        return {
            "source_map_selected_executor_input_review": True,
            "selected_review": selected_review,
            "selected_executor_input": selected_executor_input,
            "expected_action_id": selected_review.get("action_id") or "",
            "expected_consumer": "hook",
            "expected_surface": "review_hook_symbol_scope_executor_input",
            "reviewer": spec.reviewer,
        }

    @staticmethod
    def _warnings(selected_candidate: dict[str, Any]) -> list[str]:
        warnings = [
            "source_map_hook_candidate_selection_requires_selected_executor_input_review",
            "source_map_hook_candidate_selection_requires_explicit_apply_approval",
        ]
        if selected_candidate:
            warnings.append("source_map_hook_candidate_selection_does_not_install_hook")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if "source_map_hook_candidate_selection_ambiguous" in blockers:
            return "select_one_source_map_hook_candidate_by_id_or_index"
        if "source_map_hook_candidates_missing" in blockers or "source_map_hook_candidates_not_ready" in blockers:
            return "provide_ready_source_map_hook_candidates_for_selection"
        if blockers:
            return "fix_source_map_hook_candidate_selection_inputs"
        return "run_source_map_selected_executor_input_review_for_selected_hook_candidate"

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _side_effect_blockers(policy: dict[str, Any], *, prefix: str) -> list[str]:
        blockers: list[str] = []
        for key in (
            "raw_source_content_exported",
            "preview_exported",
            "fetch_source_map",
            "browser_started",
            "cdp_command_sent",
            "debugger_execution_performed",
            "runtime_evaluated",
            "breakpoint_installed",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "automatic_hook_installation",
            "automatic_loop",
            "calls_mcp",
            "mobile_runtime_used",
        ):
            if policy.get(key):
                blockers.append(f"{prefix}_{key}_detected")
        return blockers

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "breakpoint_installed": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "automatic_hook_installation": False,
            "automatic_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapDebuggerCandidateReviewSpec:
    """Review-only Source Map debugger location candidate request.

    The descriptor consumes already-reviewed Source Map lookup / symbol-scope
    metadata and optional reviewer-provided debugger locations. It never starts
    a browser, sends CDP commands, installs breakpoints, continues debugger
    execution, fetches Source Maps, exports raw source content, calls MCP, or
    touches mobile runtime chains.
    """

    bundler_symbol_scope: dict[str, Any] = field(default_factory=dict)
    source_map_lookup: dict[str, Any] = field(default_factory=dict)
    source_map_consumer_materialization: dict[str, Any] = field(default_factory=dict)
    source_map_typed_payload_preflight: dict[str, Any] = field(default_factory=dict)
    debugger_location_candidates: list[dict[str, Any]] = field(default_factory=list)
    requested_symbol: str = ""
    script_url: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapDebuggerCandidateReviewSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_debugger_candidates",
                "sourceMapDebuggerCandidates",
                "source_map_debugger_candidate_review",
                "sourceMapDebuggerCandidateReview",
                "source_map_debugger_candidate_refinement",
                "sourceMapDebuggerCandidateRefinement",
                "rank_source_map_debugger_candidates",
                "rankSourceMapDebuggerCandidates",
            )
        )
        symbol_scope = cls._object_alias(
            context,
            "bundler_symbol_scope",
            "bundler-symbol-scope",
            "bundlerSymbolScope",
            "source_map_symbol_scope",
            "sourceMapSymbolScope",
        )
        lookup = cls._object_alias(
            context,
            "source_map_lookup",
            "source-map-lookup",
            "sourceMapLookup",
            "source_map_lookup_descriptor",
            "sourceMapLookupDescriptor",
        )
        materialization = cls._object_alias(
            context,
            "source_map_consumer_materialization",
            "source-map-consumer-materialization",
            "sourceMapConsumerMaterialization",
        )
        preflight = cls._object_alias(
            context,
            "source_map_typed_payload_preflight",
            "source-map-typed-payload-preflight",
            "sourceMapTypedPayloadPreflight",
            "source_map_consumer_typed_payload_preflight",
            "sourceMapConsumerTypedPayloadPreflight",
        )
        debugger_locations = cls._dict_list_alias(
            context,
            "debugger_location_candidates",
            "debuggerLocationCandidates",
            "source_map_debugger_locations",
            "sourceMapDebuggerLocations",
            "debugger_locations",
            "debuggerLocations",
        )
        if not requested and not any((symbol_scope, lookup, materialization, preflight, debugger_locations)):
            return None
        return cls(
            bundler_symbol_scope=symbol_scope,
            source_map_lookup=lookup,
            source_map_consumer_materialization=materialization,
            source_map_typed_payload_preflight=preflight,
            debugger_location_candidates=debugger_locations,
            requested_symbol=str(context.get("symbol_name", context.get("symbolName", context.get("function_name", context.get("functionName", "")))) or ""),
            script_url=str(
                context.get(
                    "script_url",
                    context.get("scriptUrl", context.get("url_pattern", context.get("urlPattern", context.get("url", "")))),
                )
                or ""
            ),
        )

    @classmethod
    def _object_alias(cls, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        return SourceMapHookCandidateRefinementSpec._object_alias(payload, *keys)

    @staticmethod
    def _dict_list_alias(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        return SourceMapHookCandidateRefinementSpec._dict_list_alias(payload, *keys)


@dataclass(slots=True)
class SourceMapDebuggerCandidateReviewResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapDebuggerCandidateReviewManager:
    """Rank reviewed Source Map evidence into debugger location candidates."""

    def review(self, spec: SourceMapDebuggerCandidateReviewSpec | None) -> SourceMapDebuggerCandidateReviewResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapDebuggerCandidateReviewResult(status="unsupported", reason="missing_source_map_debugger_candidate_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapDebuggerCandidateReviewResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_debugger_candidate_review_failed")
            descriptor["error"] = str(exc)
            return SourceMapDebuggerCandidateReviewResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_debugger_candidate_review_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapDebuggerCandidateReviewSpec) -> dict[str, Any]:
        source_status = self._source_status(spec)
        blockers = self._input_blockers(spec, source_status)
        candidates = [] if blockers else self._candidates(spec, source_status)
        if not candidates and not blockers:
            blockers.append("source_map_debugger_candidate_review_no_candidates")
        warnings = self._warnings(candidates)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-debugger-candidates.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "candidate_review_only": True,
            "source_status": source_status,
            "requested_symbol": spec.requested_symbol or source_status.get("symbol_name", ""),
            "bundler_kind": source_status.get("bundler_kind", "unknown"),
            "source_scope_candidate_count": source_status.get("scope_candidate_count", 0),
            "lookup_candidate_count": source_status.get("lookup_candidate_count", 0),
            "explicit_debugger_location_candidate_count": len(spec.debugger_location_candidates),
            "candidate_count": len(candidates),
            "ready_for_debugger_location_review_count": sum(1 for item in candidates if item.get("ready_for_debugger_location_review")),
            "candidates": candidates,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, candidates),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-debugger-candidates.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "candidate_review_only": True,
            "reason": reason,
            "source_status": {},
            "requested_symbol": "",
            "bundler_kind": "unknown",
            "source_scope_candidate_count": 0,
            "lookup_candidate_count": 0,
            "explicit_debugger_location_candidate_count": 0,
            "candidate_count": 0,
            "ready_for_debugger_location_review_count": 0,
            "candidates": [],
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_lookup_or_bundler_symbol_scope_for_debugger_candidate_review",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _source_status(cls, spec: SourceMapDebuggerCandidateReviewSpec) -> dict[str, Any]:
        symbol_scope = spec.bundler_symbol_scope
        request = symbol_scope.get("symbol_request") if isinstance(symbol_scope.get("symbol_request"), dict) else {}
        classification = symbol_scope.get("bundler_classification") if isinstance(symbol_scope.get("bundler_classification"), dict) else {}
        scope_candidates = symbol_scope.get("scope_candidates") if isinstance(symbol_scope.get("scope_candidates"), list) else []
        return {
            "bundler_symbol_scope_present": bool(symbol_scope),
            "bundler_symbol_scope_status": cls._status(symbol_scope),
            "source_map_lookup_present": bool(spec.source_map_lookup),
            "source_map_lookup_status": cls._status(spec.source_map_lookup),
            "symbol_name": spec.requested_symbol or str(request.get("symbol_name") or ""),
            "original_source": str(request.get("original_source") or ""),
            "script_url": spec.script_url or cls._script_url_from_payloads(spec),
            "bundler_kind": classification.get("bundler_kind") or "unknown",
            "scope_candidate_count": len([item for item in scope_candidates if isinstance(item, dict)]),
            "lookup_candidate_count": len(cls._lookup_locations(spec.source_map_lookup)),
            "typed_debugger_payload_ready": cls._typed_debugger_payload_ready(spec),
            "materialization_status": cls._status(spec.source_map_consumer_materialization),
            "typed_payload_preflight_status": cls._status(spec.source_map_typed_payload_preflight),
        }

    @classmethod
    def _typed_debugger_payload_ready(cls, spec: SourceMapDebuggerCandidateReviewSpec) -> bool:
        payloads: list[dict[str, Any]] = []
        raw_materialized = spec.source_map_consumer_materialization.get("typed_review_payloads")
        if isinstance(raw_materialized, list):
            payloads.extend(item for item in raw_materialized if isinstance(item, dict))
        raw_preflight = spec.source_map_typed_payload_preflight.get("preflight_payloads")
        if isinstance(raw_preflight, list):
            payloads.extend(item for item in raw_preflight if isinstance(item, dict))
        for payload in payloads:
            if payload.get("consumer") == "debugger" and cls._status(payload) in {"ready_for_review", "ready"}:
                return True
        return False

    @classmethod
    def _input_blockers(cls, spec: SourceMapDebuggerCandidateReviewSpec, source_status: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        source_ready = False
        if source_status["bundler_symbol_scope_present"]:
            if source_status["bundler_symbol_scope_status"] in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("bundler_symbol_scope_not_ready")
            elif source_status["scope_candidate_count"] > 0:
                source_ready = True
        if source_status["source_map_lookup_present"]:
            if source_status["source_map_lookup_status"] in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_lookup_not_ready")
            elif source_status["lookup_candidate_count"] > 0:
                source_ready = True
        if spec.debugger_location_candidates:
            source_ready = True
        if not source_ready:
            blockers.append("source_map_debugger_candidate_source_evidence_missing")
        for label, payload in (
            ("bundler_symbol_scope", spec.bundler_symbol_scope),
            ("source_map_lookup", spec.source_map_lookup),
            ("source_map_consumer_materialization", spec.source_map_consumer_materialization),
            ("source_map_typed_payload_preflight", spec.source_map_typed_payload_preflight),
        ):
            policy = payload.get("side_effect_policy") if isinstance(payload.get("side_effect_policy"), dict) else {}
            blockers.extend(cls._side_effect_blockers(policy, prefix=label))
        return blockers

    @classmethod
    def _candidates(cls, spec: SourceMapDebuggerCandidateReviewSpec, source_status: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, scope_candidate in enumerate([item for item in spec.bundler_symbol_scope.get("scope_candidates", []) if isinstance(item, dict)]):
            candidate = cls._candidate_from_location(
                source_status=source_status,
                location={
                    "line_number": scope_candidate.get("generated_line_number"),
                    "column_number": scope_candidate.get("generated_column_number"),
                    "source": scope_candidate.get("original_source") or source_status.get("original_source") or "",
                    "strategy": scope_candidate.get("strategy") or "bundler-symbol-scope",
                },
                kind="source-map-symbol-generated-location",
                source_payload=scope_candidate,
                index=index,
            )
            if candidate and candidate["candidate_id"] not in seen:
                candidates.append(candidate)
                seen.add(candidate["candidate_id"])
        for index, lookup_location in enumerate(cls._lookup_locations(spec.source_map_lookup), start=len(candidates)):
            candidate = cls._candidate_from_location(
                source_status=source_status,
                location=lookup_location,
                kind="source-map-lookup-location",
                source_payload=lookup_location,
                index=index,
            )
            if candidate and candidate["candidate_id"] not in seen:
                candidates.append(candidate)
                seen.add(candidate["candidate_id"])
        for index, debugger_location in enumerate(spec.debugger_location_candidates, start=len(candidates)):
            candidate = cls._candidate_from_location(
                source_status=source_status,
                location=debugger_location,
                kind="reviewed-debugger-location",
                source_payload=debugger_location,
                index=index,
            )
            if candidate and candidate["candidate_id"] not in seen:
                candidates.append(candidate)
                seen.add(candidate["candidate_id"])
        return candidates[:20]

    @classmethod
    def _candidate_from_location(
        cls,
        *,
        source_status: dict[str, Any],
        location: dict[str, Any],
        kind: str,
        source_payload: dict[str, Any],
        index: int,
    ) -> dict[str, Any] | None:
        line_number = cls._int_alias(location, "line_number", "lineNumber", "generated_line_number", "generatedLineNumber")
        column_number = cls._int_alias(location, "column_number", "columnNumber", "generated_column_number", "generatedColumnNumber")
        url_pattern = str(
            location.get(
                "url_pattern",
                location.get("urlPattern", location.get("script_url", location.get("scriptUrl", source_status.get("script_url", "")))),
            )
            or ""
        )
        if line_number is None:
            return None
        symbol = str(source_status.get("symbol_name") or location.get("symbol_name") or location.get("symbolName") or "").strip()
        candidate_id = cls._candidate_id(kind, symbol, url_pattern, line_number, column_number, index)
        ready = bool(url_pattern) and line_number is not None
        strategy = str(location.get("mapping_strategy", location.get("strategy", "")) or "")
        review_blockers = []
        if not url_pattern:
            review_blockers.append("debugger_url_pattern_required_before_apply_review")
        return {
            "candidate_id": candidate_id,
            "candidate_kind": kind,
            "status": "ready_for_review",
            "review_required": True,
            "apply_automatically": False,
            "ready_for_debugger_location_review": ready,
            "confidence": cls._confidence(symbol, strategy, source_status, ready),
            "symbol_name": symbol,
            "original_source": location.get("source") or source_status.get("original_source") or "",
            "generated_location": {
                "url_pattern": url_pattern,
                "line_number": line_number,
                "column_number": column_number,
                "strategy": strategy,
            },
            "source_candidate": source_payload,
            "review_blockers": review_blockers,
            "suggested_debugger_location_input": {
                "url_pattern": url_pattern,
                "line_number": line_number,
                "column_number": column_number,
                "source": location.get("source") or source_status.get("original_source") or "",
                "mapping_strategy": strategy,
                "candidate_id": candidate_id,
                "cdp_command": None,
                "apply_supported_now": False,
                "requires_explicit_review": True,
            },
            "next_action": "review_source_map_debugger_location_input" if ready else "add_url_pattern_before_debugger_location_review",
        }

    @classmethod
    def _lookup_locations(cls, lookup: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for key in ("generated_location", "location", "result", "mapping"):
            value = lookup.get(key)
            if isinstance(value, dict):
                candidates.append(value)
        for key in ("generated_locations", "locations", "candidates"):
            value = lookup.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))
        return candidates

    @staticmethod
    def _candidate_id(kind: str, symbol: str, url_pattern: str, line_number: int, column_number: int | None, index: int) -> str:
        safe_symbol = re.sub(r"[^A-Za-z0-9_.:$-]+", "_", symbol or "anonymous")[:80]
        digest = hashlib.sha256(f"{kind}|{url_pattern}|{line_number}|{column_number}|{index}".encode("utf-8")).hexdigest()[:10]
        return f"source-map-debugger:{kind}:{safe_symbol}:{line_number}:{column_number if column_number is not None else 'x'}:{digest}"

    @staticmethod
    def _confidence(symbol: str, strategy: str, source_status: dict[str, Any], ready: bool) -> dict[str, Any]:
        score = 0.45
        signals: list[str] = []
        if symbol:
            score += 0.1
            signals.append("symbol_name_present")
        if strategy in {"source_map_name", "source_map_generated_exact", "exact", "generated_exact"}:
            score += 0.2
            signals.append(strategy)
        elif strategy:
            score += 0.1
            signals.append(strategy)
        if source_status.get("typed_debugger_payload_ready"):
            score += 0.1
            signals.append("typed_debugger_payload_ready")
        if ready:
            score += 0.15
            signals.append("debugger_location_input_reviewable")
        score = min(score, 0.95)
        label = "high" if score >= 0.8 else "medium" if score >= 0.55 else "low"
        return {"score": round(score, 2), "label": label, "signals": signals}

    @staticmethod
    def _warnings(candidates: list[dict[str, Any]]) -> list[str]:
        warnings = [
            "source_map_debugger_candidates_require_explicit_review_before_apply",
            "automatic_debugger_continuation_not_supported",
        ]
        if candidates and not any(item.get("ready_for_debugger_location_review") for item in candidates):
            warnings.append("debugger_location_inputs_still_required")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], candidates: list[dict[str, Any]]) -> str:
        if "source_map_debugger_candidate_source_evidence_missing" in blockers:
            return "provide_source_map_lookup_or_bundler_symbol_scope_for_debugger_candidates"
        if blockers:
            return "fix_source_map_debugger_candidate_review_inputs"
        if any(item.get("ready_for_debugger_location_review") for item in candidates):
            return "review_source_map_debugger_candidates_before_selected_debugger_apply"
        return "add_debugger_url_pattern_before_selected_debugger_apply"

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _int_alias(payload: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            if key not in payload:
                continue
            value = payload.get(key)
            if value is None or value == "":
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _script_url_from_payloads(spec: SourceMapDebuggerCandidateReviewSpec) -> str:
        for payload in (spec.source_map_lookup, spec.bundler_symbol_scope):
            for key in ("script_url", "scriptUrl", "url_pattern", "urlPattern", "url"):
                value = payload.get(key)
                if value:
                    return str(value)
        return ""

    @staticmethod
    def _side_effect_blockers(policy: dict[str, Any], *, prefix: str) -> list[str]:
        blockers: list[str] = []
        for key in (
            "raw_source_content_exported",
            "preview_exported",
            "fetch_source_map",
            "browser_started",
            "cdp_command_sent",
            "debugger_execution_performed",
            "runtime_evaluated",
            "breakpoint_installed",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "calls_mcp",
            "mobile_runtime_used",
        ):
            if policy.get(key):
                blockers.append(f"{prefix}_{key}_detected")
        return blockers

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "candidate_review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "breakpoint_installed": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "automatic_debugger_continuation": False,
            "automatic_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapDebuggerCandidateSelectionSpec:
    """Review-only handoff from debugger candidates to selected executor input review."""

    source_map_debugger_candidates: dict[str, Any] = field(default_factory=dict)
    selected_candidate_id: str = ""
    selected_candidate_index: int | None = None
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapDebuggerCandidateSelectionSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_debugger_candidate_selection",
                "sourceMapDebuggerCandidateSelection",
                "source_map_debugger_candidate_handoff",
                "sourceMapDebuggerCandidateHandoff",
                "select_source_map_debugger_candidate",
                "selectSourceMapDebuggerCandidate",
                "source_map_debugger_candidate_executor_input",
                "sourceMapDebuggerCandidateExecutorInput",
            )
        )
        candidates = SourceMapHookCandidateRefinementSpec._object_alias(
            context,
            "source_map_debugger_candidates",
            "source-map-debugger-candidates",
            "sourceMapDebuggerCandidates",
            "source_map_debugger_candidate_review",
            "sourceMapDebuggerCandidateReview",
            "source_map_debugger_candidate_refinement",
            "sourceMapDebuggerCandidateRefinement",
        )
        selected_index = cls._optional_int(context.get("selected_candidate_index", context.get("selectedCandidateIndex", context.get("candidate_index", context.get("candidateIndex")))))
        selected_id = str(context.get("selected_candidate_id", context.get("selectedCandidateId", context.get("candidate_id", context.get("candidateId", "")))) or "")
        if not requested and not candidates and not selected_id and selected_index is None:
            return None
        return cls(
            source_map_debugger_candidates=candidates,
            selected_candidate_id=selected_id,
            selected_candidate_index=selected_index,
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


@dataclass(slots=True)
class SourceMapDebuggerCandidateSelectionResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapDebuggerCandidateSelectionManager:
    """Select one reviewed debugger candidate and build downstream review input."""

    def review(self, spec: SourceMapDebuggerCandidateSelectionSpec | None) -> SourceMapDebuggerCandidateSelectionResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapDebuggerCandidateSelectionResult(status="unsupported", reason="missing_source_map_debugger_candidate_selection_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapDebuggerCandidateSelectionResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_debugger_candidate_selection_failed")
            descriptor["error"] = str(exc)
            return SourceMapDebuggerCandidateSelectionResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_debugger_candidate_selection_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapDebuggerCandidateSelectionSpec) -> dict[str, Any]:
        candidates_payload = spec.source_map_debugger_candidates
        candidates = [item for item in candidates_payload.get("candidates", []) if isinstance(item, dict)] if isinstance(candidates_payload.get("candidates"), list) else []
        blockers = self._input_blockers(candidates_payload, candidates, spec)
        selected_index, selected_candidate = self._select_candidate(candidates, spec, blockers)
        selected_executor_input = {} if blockers or not selected_candidate else self._selected_executor_input(selected_candidate)
        selected_review = {} if blockers or not selected_executor_input else self._selected_review(selected_candidate, selected_executor_input, spec)
        review_context = {} if blockers or not selected_review else self._selected_executor_input_review_context(selected_review, selected_executor_input, spec)
        if selected_executor_input:
            blockers.extend(SourceMapSelectedExecutorInputReviewManager._consumer_executor_input_blockers("debugger", selected_executor_input))
        warnings = self._warnings(selected_candidate)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-debugger-candidate-selection.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "source_candidates_schema_version": str(candidates_payload.get("schema_version") or ""),
            "source_candidates_status": self._status(candidates_payload),
            "candidate_count": len(candidates),
            "ready_for_debugger_location_review_count": sum(1 for item in candidates if item.get("ready_for_debugger_location_review")),
            "selected_candidate_id": str(selected_candidate.get("candidate_id") or "") if selected_candidate else "",
            "selected_candidate_index": selected_index,
            "selected_candidate": selected_candidate or {},
            "selected_action_id": str(selected_review.get("action_id") or ""),
            "selected_consumer": "debugger" if selected_review else "",
            "selected_followthrough_review_surface": str(selected_review.get("followthrough_review_surface") or ""),
            "selected_review": selected_review,
            "selected_executor_input": selected_executor_input,
            "source_map_selected_executor_input_review_context": review_context,
            "ready_for_selected_executor_input_review": bool(review_context) and not blockers,
            "reviewer": spec.reviewer,
            "debugger_execution_performed": False,
            "breakpoint_installed": False,
            "automatic_debugger_continuation": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-debugger-candidate-selection.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_candidates_schema_version": "",
            "source_candidates_status": "",
            "candidate_count": 0,
            "ready_for_debugger_location_review_count": 0,
            "selected_candidate_id": "",
            "selected_candidate_index": None,
            "selected_candidate": {},
            "selected_action_id": "",
            "selected_consumer": "",
            "selected_followthrough_review_surface": "",
            "selected_review": {},
            "selected_executor_input": {},
            "source_map_selected_executor_input_review_context": {},
            "ready_for_selected_executor_input_review": False,
            "reviewer": "",
            "debugger_execution_performed": False,
            "breakpoint_installed": False,
            "automatic_debugger_continuation": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_debugger_candidates_for_selection",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, payload: dict[str, Any], candidates: list[dict[str, Any]], spec: SourceMapDebuggerCandidateSelectionSpec) -> list[str]:
        blockers: list[str] = []
        if not payload:
            blockers.append("source_map_debugger_candidates_missing")
        elif payload.get("schema_version") not in {None, "", "reverse-deepagent.source-map-debugger-candidates.v1"}:
            blockers.append("source_map_debugger_candidates_schema_mismatch")
        status = cls._status(payload)
        if status in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_debugger_candidates_not_ready")
        if not candidates:
            blockers.append("source_map_debugger_candidates_empty")
        if len(candidates) > 1 and not spec.selected_candidate_id and spec.selected_candidate_index is None:
            blockers.append("source_map_debugger_candidate_selection_ambiguous")
        policy = payload.get("side_effect_policy") if isinstance(payload.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_debugger_candidates"))
        if payload.get("debugger_execution_performed") is True or payload.get("breakpoint_installed") is True:
            blockers.append("source_map_debugger_candidates_unexpected_execution")
        return blockers

    @classmethod
    def _select_candidate(
        cls,
        candidates: list[dict[str, Any]],
        spec: SourceMapDebuggerCandidateSelectionSpec,
        blockers: list[str],
    ) -> tuple[int | None, dict[str, Any]]:
        if not candidates:
            return None, {}
        selected_index: int | None = None
        selected: dict[str, Any] = {}
        if spec.selected_candidate_id:
            for index, candidate in enumerate(candidates):
                if str(candidate.get("candidate_id") or "") == spec.selected_candidate_id:
                    selected_index = index
                    selected = candidate
                    break
            if not selected:
                blockers.append("source_map_debugger_selected_candidate_id_not_found")
                return None, {}
        elif spec.selected_candidate_index is not None:
            if spec.selected_candidate_index < 0 or spec.selected_candidate_index >= len(candidates):
                blockers.append("source_map_debugger_selected_candidate_index_out_of_range")
                return None, {}
            selected_index = spec.selected_candidate_index
            selected = candidates[selected_index]
        elif len(candidates) == 1:
            selected_index = 0
            selected = candidates[0]
        else:
            return None, {}
        if selected.get("ready_for_debugger_location_review") is not True:
            blockers.append("source_map_debugger_selected_candidate_not_ready_for_location_review")
        if selected.get("apply_automatically") is True:
            blockers.append("source_map_debugger_selected_candidate_auto_apply_claim_detected")
        return selected_index, selected

    @staticmethod
    def _selected_executor_input(candidate: dict[str, Any]) -> dict[str, Any]:
        suggested = candidate.get("suggested_debugger_location_input") if isinstance(candidate.get("suggested_debugger_location_input"), dict) else {}
        generated = candidate.get("generated_location") if isinstance(candidate.get("generated_location"), dict) else {}
        location = {
            "url_pattern": suggested.get("url_pattern") or generated.get("url_pattern") or "",
            "line_number": suggested.get("line_number") if suggested.get("line_number") is not None else generated.get("line_number"),
            "column_number": suggested.get("column_number") if suggested.get("column_number") is not None else generated.get("column_number"),
            "source": suggested.get("source") or candidate.get("original_source") or "",
            "mapping_strategy": suggested.get("mapping_strategy") or generated.get("strategy") or "",
            "candidate_id": candidate.get("candidate_id") or "",
        }
        return {
            "location": location,
            "cdp_command": None,
            "requires_review_before_debugger_use": True,
            "source_map_debugger_candidate_id": candidate.get("candidate_id") or "",
        }

    @staticmethod
    def _selected_review(candidate: dict[str, Any], selected_executor_input: dict[str, Any], spec: SourceMapDebuggerCandidateSelectionSpec) -> dict[str, Any]:
        candidate_id = str(candidate.get("candidate_id") or "")
        action_id = f"source-map-debugger-candidate:{candidate_id}"
        return {
            "status": "ready_for_review",
            "action_id": action_id,
            "consumer": "debugger",
            "followthrough_review_surface": "review_debugger_location_executor_input",
            "review_required": True,
            "explicit_review_required": True,
            "execute_automatically": False,
            "executor_invoked": False,
            "executor_input": selected_executor_input,
            "review_prompt": "Review selected Source Map debugger candidate before any CDP breakpoint command.",
            "next_action": "review_selected_source_map_debugger_candidate_input",
            "reviewer": spec.reviewer,
            "source_candidate_id": candidate_id,
            "side_effect_policy": SourceMapDebuggerCandidateSelectionManager._side_effect_policy(),
        }

    @staticmethod
    def _selected_executor_input_review_context(selected_review: dict[str, Any], selected_executor_input: dict[str, Any], spec: SourceMapDebuggerCandidateSelectionSpec) -> dict[str, Any]:
        return {
            "source_map_selected_executor_input_review": True,
            "selected_review": selected_review,
            "selected_executor_input": selected_executor_input,
            "expected_action_id": selected_review.get("action_id") or "",
            "expected_consumer": "debugger",
            "expected_surface": "review_debugger_location_executor_input",
            "reviewer": spec.reviewer,
        }

    @staticmethod
    def _warnings(selected_candidate: dict[str, Any]) -> list[str]:
        warnings = [
            "source_map_debugger_candidate_selection_requires_selected_executor_input_review",
            "source_map_debugger_candidate_selection_requires_explicit_apply_approval",
        ]
        if selected_candidate:
            warnings.append("source_map_debugger_candidate_selection_does_not_apply_breakpoint")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if "source_map_debugger_candidate_selection_ambiguous" in blockers:
            return "select_one_source_map_debugger_candidate_by_id_or_index"
        if "source_map_debugger_candidates_missing" in blockers or "source_map_debugger_candidates_not_ready" in blockers:
            return "provide_ready_source_map_debugger_candidates_for_selection"
        if blockers:
            return "fix_source_map_debugger_candidate_selection_inputs"
        return "run_source_map_selected_executor_input_review_for_selected_debugger_candidate"

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _side_effect_blockers(policy: dict[str, Any], *, prefix: str) -> list[str]:
        blockers: list[str] = []
        for key in (
            "raw_source_content_exported",
            "preview_exported",
            "fetch_source_map",
            "browser_started",
            "cdp_command_sent",
            "debugger_execution_performed",
            "runtime_evaluated",
            "breakpoint_installed",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "automatic_debugger_continuation",
            "automatic_loop",
            "calls_mcp",
            "mobile_runtime_used",
        ):
            if policy.get(key):
                blockers.append(f"{prefix}_{key}_detected")
        return blockers

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "selection_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "breakpoint_installed": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "automatic_debugger_continuation": False,
            "automatic_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapSelectedExecutorInputReviewSpec:
    """Review-only package for one selected Source Map follow-through executor input.

    This consumes the Step 273 surface-selection descriptor and turns the chosen
    debugger / source-logpoint / rebuild / hook executor input into a stable
    downstream review package.  It does not invoke that executor.
    """

    source_map_followthrough_surface_selection: dict[str, Any] = field(default_factory=dict)
    source_map_debugger_candidate_selection: dict[str, Any] = field(default_factory=dict)
    source_map_hook_candidate_selection: dict[str, Any] = field(default_factory=dict)
    selected_review: dict[str, Any] = field(default_factory=dict)
    selected_executor_input: dict[str, Any] = field(default_factory=dict)
    expected_action_id: str = ""
    expected_consumer: str = ""
    expected_surface: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapSelectedExecutorInputReviewSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_selected_executor_input_review",
                "sourceMapSelectedExecutorInputReview",
                "source_map_followthrough_executor_input_review",
                "sourceMapFollowthroughExecutorInputReview",
                "source_map_selected_followthrough_review",
                "sourceMapSelectedFollowthroughReview",
                "source_map_debugger_candidate_selected_input_review",
                "sourceMapDebuggerCandidateSelectedInputReview",
                "source_map_debugger_candidate_executor_input_review",
                "sourceMapDebuggerCandidateExecutorInputReview",
                "source_map_hook_candidate_selected_input_review",
                "sourceMapHookCandidateSelectedInputReview",
                "source_map_hook_candidate_executor_input_review",
                "sourceMapHookCandidateExecutorInputReview",
                "source_map_hook_candidate_selected_executor_input_review",
                "sourceMapHookCandidateSelectedExecutorInputReview",
            )
        )
        selection = cls._object_alias(
            context,
            "source_map_followthrough_surface_selection",
            "source-map-followthrough-surface-selection",
            "sourceMapFollowthroughSurfaceSelection",
            "source_map_followthrough_surface_review",
            "source-map-followthrough-surface-review",
            "sourceMapFollowthroughSurfaceReview",
            "source_map_selected_surface_selection",
            "sourceMapSelectedSurfaceSelection",
        )
        debugger_candidate_selection = cls._object_alias(
            context,
            "source_map_debugger_candidate_selection",
            "source-map-debugger-candidate-selection",
            "sourceMapDebuggerCandidateSelection",
            "source_map_debugger_candidate_handoff",
            "sourceMapDebuggerCandidateHandoff",
            "source_map_selected_debugger_candidate",
            "sourceMapSelectedDebuggerCandidate",
        )
        debugger_candidate_review_context = (
            debugger_candidate_selection.get("source_map_selected_executor_input_review_context")
            if isinstance(debugger_candidate_selection.get("source_map_selected_executor_input_review_context"), dict)
            else {}
        )
        hook_candidate_selection = cls._object_alias(
            context,
            "source_map_hook_candidate_selection",
            "source-map-hook-candidate-selection",
            "sourceMapHookCandidateSelection",
            "source_map_hook_candidate_handoff",
            "sourceMapHookCandidateHandoff",
            "source_map_selected_hook_candidate",
            "sourceMapSelectedHookCandidate",
        )
        hook_candidate_review_context = (
            hook_candidate_selection.get("source_map_selected_executor_input_review_context")
            if isinstance(hook_candidate_selection.get("source_map_selected_executor_input_review_context"), dict)
            else {}
        )
        selected_review = cls._object_alias(context, "selected_review", "selectedReview", "source_map_selected_review", "sourceMapSelectedReview")
        executor_input = cls._object_alias(
            context,
            "selected_executor_input",
            "selectedExecutorInput",
            "source_map_selected_executor_input",
            "sourceMapSelectedExecutorInput",
            "executor_input",
            "executorInput",
        )
        if not selected_review and selection:
            value = selection.get("selected_review")
            selected_review = value if isinstance(value, dict) else {}
        if not executor_input and selection:
            value = selection.get("selected_executor_input")
            executor_input = value if isinstance(value, dict) else {}
        if not selected_review and debugger_candidate_review_context:
            value = debugger_candidate_review_context.get("selected_review")
            selected_review = value if isinstance(value, dict) else {}
        if not executor_input and debugger_candidate_review_context:
            value = debugger_candidate_review_context.get("selected_executor_input")
            executor_input = value if isinstance(value, dict) else {}
        if not selected_review and hook_candidate_review_context:
            value = hook_candidate_review_context.get("selected_review")
            selected_review = value if isinstance(value, dict) else {}
        if not executor_input and hook_candidate_review_context:
            value = hook_candidate_review_context.get("selected_executor_input")
            executor_input = value if isinstance(value, dict) else {}
        if not requested and not selection and not debugger_candidate_selection and not hook_candidate_selection and not selected_review and not executor_input:
            return None
        expected_action_id = str(
            context.get(
                "source_map_selected_action_id",
                context.get("sourceMapSelectedActionId", context.get("expected_action_id", context.get("expectedActionId", ""))),
            )
            or ""
        )
        expected_consumer = str(
            context.get(
                "source_map_selected_consumer",
                context.get("sourceMapSelectedConsumer", context.get("expected_consumer", context.get("expectedConsumer", ""))),
            )
            or ""
        )
        expected_surface = str(
            context.get(
                "source_map_selected_surface",
                context.get("sourceMapSelectedSurface", context.get("expected_surface", context.get("expectedSurface", ""))),
            )
            or ""
        )
        if not expected_action_id and debugger_candidate_review_context:
            expected_action_id = str(debugger_candidate_review_context.get("expected_action_id") or debugger_candidate_review_context.get("expectedActionId") or "")
        if not expected_action_id and hook_candidate_review_context:
            expected_action_id = str(hook_candidate_review_context.get("expected_action_id") or hook_candidate_review_context.get("expectedActionId") or "")
        if not expected_consumer and debugger_candidate_review_context:
            expected_consumer = str(debugger_candidate_review_context.get("expected_consumer") or debugger_candidate_review_context.get("expectedConsumer") or "")
        if not expected_consumer and hook_candidate_review_context:
            expected_consumer = str(hook_candidate_review_context.get("expected_consumer") or hook_candidate_review_context.get("expectedConsumer") or "")
        if not expected_surface and debugger_candidate_review_context:
            expected_surface = str(debugger_candidate_review_context.get("expected_surface") or debugger_candidate_review_context.get("expectedSurface") or "")
        if not expected_surface and hook_candidate_review_context:
            expected_surface = str(hook_candidate_review_context.get("expected_surface") or hook_candidate_review_context.get("expectedSurface") or "")
        reviewer = str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or "")
        if not reviewer and debugger_candidate_review_context:
            reviewer = str(debugger_candidate_review_context.get("reviewer") or debugger_candidate_review_context.get("reviewer_id") or debugger_candidate_review_context.get("reviewerId") or "")
        if not reviewer and hook_candidate_review_context:
            reviewer = str(hook_candidate_review_context.get("reviewer") or hook_candidate_review_context.get("reviewer_id") or hook_candidate_review_context.get("reviewerId") or "")
        return cls(
            source_map_followthrough_surface_selection=selection,
            source_map_debugger_candidate_selection=debugger_candidate_selection,
            source_map_hook_candidate_selection=hook_candidate_selection,
            selected_review=selected_review,
            selected_executor_input=executor_input,
            expected_action_id=expected_action_id,
            expected_consumer=expected_consumer,
            expected_surface=expected_surface,
            reviewer=reviewer,
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapSelectedExecutorInputReviewResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapSelectedExecutorInputReviewManager:
    """Preflight one selected Source Map follow-through executor input for review."""

    def review(self, spec: SourceMapSelectedExecutorInputReviewSpec | None) -> SourceMapSelectedExecutorInputReviewResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapSelectedExecutorInputReviewResult(status="unsupported", reason="missing_source_map_selected_executor_input_review_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapSelectedExecutorInputReviewResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_selected_executor_input_review_failed")
            descriptor["error"] = str(exc)
            return SourceMapSelectedExecutorInputReviewResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_selected_executor_input_review_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapSelectedExecutorInputReviewSpec) -> dict[str, Any]:
        selection = spec.source_map_followthrough_surface_selection
        debugger_candidate_selection = spec.source_map_debugger_candidate_selection
        hook_candidate_selection = spec.source_map_hook_candidate_selection
        selected_review = dict(spec.selected_review) if isinstance(spec.selected_review, dict) else {}
        executor_input = dict(spec.selected_executor_input) if isinstance(spec.selected_executor_input, dict) else {}
        blockers = self._input_blockers(selection, selected_review, executor_input)
        blockers.extend(self._debugger_candidate_selection_blockers(debugger_candidate_selection))
        blockers.extend(self._hook_candidate_selection_blockers(hook_candidate_selection))
        blockers.extend(self._expectation_blockers(spec, selected_review, selection))
        if selected_review:
            blockers.extend(self._selected_review_blockers(selected_review, executor_input))
        package = {} if blockers else self._executor_review_package(selection, selected_review, executor_input, spec)
        blockers.extend(self._package_blockers(package))
        warnings = self._warnings(selection, debugger_candidate_selection, selected_review, package, hook_candidate_selection)
        status = "blocked" if blockers else "ready_for_review"
        consumer = str(selected_review.get("consumer") or selection.get("selected_consumer") or "")
        surface = str(selected_review.get("followthrough_review_surface") or selection.get("selected_followthrough_review_surface") or "")
        action_id = str(selected_review.get("action_id") or selection.get("selected_action_id") or "")
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-input-review.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "preflight_only": True,
            "executor_input_review_only": True,
            "handoff_only": True,
            "source_surface_selection_schema_version": str(selection.get("schema_version") or ""),
            "source_surface_selection_status": self._status(selection),
            "source_debugger_candidate_selection_schema_version": str(debugger_candidate_selection.get("schema_version") or ""),
            "source_debugger_candidate_selection_status": self._status(debugger_candidate_selection),
            "source_debugger_candidate_selection_id": str(debugger_candidate_selection.get("selected_candidate_id") or ""),
            "source_debugger_candidate_selection_ready": bool(debugger_candidate_selection.get("ready_for_selected_executor_input_review", False)),
            "source_hook_candidate_selection_schema_version": str(hook_candidate_selection.get("schema_version") or ""),
            "source_hook_candidate_selection_status": self._status(hook_candidate_selection),
            "source_hook_candidate_selection_id": str(hook_candidate_selection.get("selected_candidate_id") or ""),
            "source_hook_candidate_selection_ready": bool(hook_candidate_selection.get("ready_for_selected_executor_input_review", False)),
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_followthrough_review_surface": surface,
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "expected_surface": spec.expected_surface,
            "reviewer": spec.reviewer,
            "selected_review": selected_review,
            "selected_executor_input": executor_input,
            "executor_review_package": package,
            "executor_review_package_ready": bool(package) and not blockers,
            "downstream_review_prompt": str(package.get("review_prompt") or selected_review.get("review_prompt") or selection.get("downstream_review_prompt") or ""),
            "downstream_next_action": str(package.get("next_action") or selected_review.get("next_action") or selection.get("downstream_next_action") or ""),
            "ready_for_executor_review": bool(package) and not blockers,
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, package, consumer),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-input-review.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "preflight_only": True,
            "executor_input_review_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_surface_selection_schema_version": "",
            "source_surface_selection_status": "",
            "source_debugger_candidate_selection_schema_version": "",
            "source_debugger_candidate_selection_status": "",
            "source_debugger_candidate_selection_id": "",
            "source_debugger_candidate_selection_ready": False,
            "source_hook_candidate_selection_schema_version": "",
            "source_hook_candidate_selection_status": "",
            "source_hook_candidate_selection_id": "",
            "source_hook_candidate_selection_ready": False,
            "selected_action_id": "",
            "selected_consumer": "",
            "selected_followthrough_review_surface": "",
            "expected_action_id": "",
            "expected_consumer": "",
            "expected_surface": "",
            "reviewer": "",
            "selected_review": {},
            "selected_executor_input": {},
            "executor_review_package": {},
            "executor_review_package_ready": False,
            "downstream_review_prompt": "",
            "downstream_next_action": "",
            "ready_for_executor_review": False,
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_surface_selection_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, selection: dict[str, Any], selected_review: dict[str, Any], executor_input: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not selection and not selected_review and not executor_input:
            blockers.append("source_map_followthrough_surface_selection_missing")
        if selection:
            if selection.get("schema_version") not in {None, "", "reverse-deepagent.source-map-followthrough-surface-selection.v1"}:
                blockers.append("source_map_followthrough_surface_selection_schema_mismatch")
            if cls._status(selection) in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_followthrough_surface_selection_not_ready")
            if selection.get("ready_for_surface_review") is not True:
                blockers.append("source_map_followthrough_surface_selection_not_ready_for_executor_review")
            if selection.get("surface_executor_invoked") is True:
                blockers.append("source_map_followthrough_surface_selection_executor_invoked")
            blockers.extend(f"source_map_followthrough_surface_selection:{item}" for item in cls._string_list(selection.get("blockers")))
            policy = selection.get("side_effect_policy") if isinstance(selection.get("side_effect_policy"), dict) else {}
            blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_followthrough_surface_selection"))
        if not selected_review:
            blockers.append("selected_followthrough_review_missing")
        if not executor_input:
            blockers.append("selected_executor_input_missing")
        return blockers

    @classmethod
    def _debugger_candidate_selection_blockers(cls, debugger_candidate_selection: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not debugger_candidate_selection:
            return blockers
        if debugger_candidate_selection.get("schema_version") not in {None, "", "reverse-deepagent.source-map-debugger-candidate-selection.v1"}:
            blockers.append("source_map_debugger_candidate_selection_schema_mismatch")
        if cls._status(debugger_candidate_selection) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_debugger_candidate_selection_not_ready")
        if debugger_candidate_selection.get("ready_for_selected_executor_input_review") is not True:
            blockers.append("source_map_debugger_candidate_selection_not_ready_for_input_review")
        if debugger_candidate_selection.get("debugger_execution_performed") is True:
            blockers.append("source_map_debugger_candidate_selection_debugger_executed")
        if debugger_candidate_selection.get("breakpoint_installed") is True:
            blockers.append("source_map_debugger_candidate_selection_breakpoint_installed")
        blockers.extend(f"source_map_debugger_candidate_selection:{item}" for item in cls._string_list(debugger_candidate_selection.get("blockers")))
        policy = debugger_candidate_selection.get("side_effect_policy") if isinstance(debugger_candidate_selection.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_debugger_candidate_selection"))
        review_context = debugger_candidate_selection.get("source_map_selected_executor_input_review_context")
        if not isinstance(review_context, dict) or not review_context:
            blockers.append("source_map_debugger_candidate_selection_review_context_missing")
        return blockers

    @classmethod
    def _hook_candidate_selection_blockers(cls, hook_candidate_selection: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not hook_candidate_selection:
            return blockers
        if hook_candidate_selection.get("schema_version") not in {None, "", "reverse-deepagent.source-map-hook-candidate-selection.v1"}:
            blockers.append("source_map_hook_candidate_selection_schema_mismatch")
        if cls._status(hook_candidate_selection) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_hook_candidate_selection_not_ready")
        if hook_candidate_selection.get("ready_for_selected_executor_input_review") is not True:
            blockers.append("source_map_hook_candidate_selection_not_ready_for_input_review")
        if hook_candidate_selection.get("hook_installed") is True:
            blockers.append("source_map_hook_candidate_selection_hook_installed")
        if hook_candidate_selection.get("automatic_hook_installation") is True:
            blockers.append("source_map_hook_candidate_selection_automatic_hook_installation")
        blockers.extend(f"source_map_hook_candidate_selection:{item}" for item in cls._string_list(hook_candidate_selection.get("blockers")))
        policy = hook_candidate_selection.get("side_effect_policy") if isinstance(hook_candidate_selection.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_hook_candidate_selection"))
        review_context = hook_candidate_selection.get("source_map_selected_executor_input_review_context")
        if not isinstance(review_context, dict) or not review_context:
            blockers.append("source_map_hook_candidate_selection_review_context_missing")
        return blockers

    @staticmethod
    def _expectation_blockers(spec: SourceMapSelectedExecutorInputReviewSpec, selected_review: dict[str, Any], selection: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        action_id = str(selected_review.get("action_id") or selection.get("selected_action_id") or "")
        consumer = str(selected_review.get("consumer") or selection.get("selected_consumer") or "")
        surface = str(selected_review.get("followthrough_review_surface") or selection.get("selected_followthrough_review_surface") or "")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_consumer and consumer and spec.expected_consumer != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_surface and surface and spec.expected_surface != surface:
            blockers.append("selected_followthrough_surface_mismatch")
        return blockers

    @classmethod
    def _selected_review_blockers(cls, selected_review: dict[str, Any], executor_input: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        consumer = str(selected_review.get("consumer") or "")
        surface = str(selected_review.get("followthrough_review_surface") or "")
        if cls._status(selected_review) not in {"ready_for_review", "ready"}:
            blockers.append("selected_followthrough_review_not_ready")
        if selected_review.get("explicit_review_required") is not True:
            blockers.append("selected_followthrough_explicit_review_required_missing")
        if selected_review.get("review_required") is not True:
            blockers.append("selected_followthrough_review_required_missing")
        if selected_review.get("execute_automatically") is True:
            blockers.append("selected_followthrough_auto_execution_claim_detected")
        if selected_review.get("executor_invoked") is True:
            blockers.append("selected_followthrough_executor_invoked")
        blockers.extend(cls._side_effect_blockers(selected_review.get("side_effect_policy") if isinstance(selected_review.get("side_effect_policy"), dict) else {}, prefix="selected_followthrough_review"))
        if selected_review.get("executor_input") and selected_review.get("executor_input") != executor_input:
            blockers.append("selected_executor_input_mismatch")
        if consumer not in {"debugger", "source-logpoint", "rebuild", "hook"}:
            blockers.append("selected_consumer_unsupported")
        expected_surface = {
            "debugger": "review_debugger_location_executor_input",
            "source-logpoint": "review_source_logpoint_executor_input",
            "rebuild": "review_rebuild_source_metadata_executor_input",
            "hook": "review_hook_symbol_scope_executor_input",
        }.get(consumer)
        if expected_surface and surface != expected_surface:
            blockers.append("selected_followthrough_surface_consumer_mismatch")
        blockers.extend(cls._consumer_executor_input_blockers(consumer, executor_input))
        return blockers

    @staticmethod
    def _consumer_executor_input_blockers(consumer: str, executor_input: dict[str, Any]) -> list[str]:
        if consumer == "debugger":
            return SourceMapTypedPayloadPreflightManager._debugger_blockers("debugger-location-review", executor_input)
        if consumer == "source-logpoint":
            return SourceMapTypedPayloadPreflightManager._source_logpoint_blockers("source-logpoint-plan-review", executor_input)
        if consumer == "rebuild":
            return SourceMapTypedPayloadPreflightManager._rebuild_blockers("rebuild-source-metadata-review", executor_input)
        if consumer == "hook":
            return SourceMapTypedPayloadPreflightManager._hook_blockers("hook-symbol-scope-review", executor_input)
        return []

    @classmethod
    def _executor_review_package(cls, selection: dict[str, Any], selected_review: dict[str, Any], executor_input: dict[str, Any], spec: SourceMapSelectedExecutorInputReviewSpec) -> dict[str, Any]:
        consumer = str(selected_review.get("consumer") or selection.get("selected_consumer") or "")
        surface = str(selected_review.get("followthrough_review_surface") or selection.get("selected_followthrough_review_surface") or "")
        action_id = str(selected_review.get("action_id") or selection.get("selected_action_id") or "")
        gate = cls._review_gate(consumer)
        return {
            "package_version": "reverse-deepagent.source-map-selected-executor-input-review.package.v1",
            "action_id": action_id,
            "consumer": consumer,
            "followthrough_review_surface": surface,
            "review_prompt": str(selected_review.get("review_prompt") or selection.get("downstream_review_prompt") or gate.get("review_prompt") or ""),
            "next_action": str(selected_review.get("next_action") or selection.get("downstream_next_action") or gate.get("next_action") or ""),
            "executor_input": executor_input,
            "review_gate": gate,
            "reviewer": spec.reviewer,
            "requires_explicit_review": True,
            "ready_for_downstream_review": True,
            "execute_automatically": False,
            "executor_invoked": False,
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _review_gate(consumer: str) -> dict[str, Any]:
        gates = {
            "debugger": {
                "gate": "explicit_debugger_location_review",
                "required_approval_flag": "review_approved",
                "forbidden_without_review": ["Debugger.resume", "Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut", "Debugger.evaluateOnCallFrame"],
                "next_action": "review_debugger_location_before_cdp_command",
                "review_prompt": "Review debugger location executor input before any CDP Debugger command.",
            },
            "source-logpoint": {
                "gate": "explicit_source_logpoint_install_review",
                "required_approval_flag": "review_approved",
                "forbidden_without_review": ["source_logpoint_install", "Runtime.evaluate", "Debugger.setBreakpoint"],
                "next_action": "review_source_logpoint_plan_before_installation",
                "review_prompt": "Review source-logpoint plan before installation.",
            },
            "rebuild": {
                "gate": "explicit_rebuild_source_metadata_review",
                "required_approval_flag": "review_approved",
                "forbidden_without_review": ["rebuild_generation", "raw_source_export"],
                "next_action": "review_rebuild_source_metadata_before_generation",
                "review_prompt": "Review digest-only rebuild metadata before generation.",
            },
            "hook": {
                "gate": "explicit_hook_symbol_scope_review",
                "required_approval_flag": "review_approved",
                "forbidden_without_review": ["runtime_hook_install", "Runtime.evaluate", "Debugger.evaluateOnCallFrame"],
                "next_action": "review_hook_symbol_scope_before_runtime_hook",
                "review_prompt": "Review hook symbol scope candidate before runtime hook installation.",
            },
        }
        return gates.get(consumer, {"gate": "unsupported_source_map_followthrough_consumer", "required_approval_flag": "review_approved", "forbidden_without_review": [], "next_action": "choose_supported_source_map_followthrough_consumer", "review_prompt": "Choose a supported Source Map follow-through consumer."})

    @classmethod
    def _package_blockers(cls, package: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not package:
            return blockers
        if package.get("requires_explicit_review") is not True:
            blockers.append("executor_review_package_explicit_review_missing")
        if package.get("execute_automatically") is True or package.get("executor_invoked") is True:
            blockers.append("executor_review_package_execution_claim_detected")
        blockers.extend(cls._side_effect_blockers(package.get("side_effect_policy") if isinstance(package.get("side_effect_policy"), dict) else {}, prefix="executor_review_package"))
        if not isinstance(package.get("executor_input"), dict) or not package.get("executor_input"):
            blockers.append("executor_review_package_input_missing")
        if not isinstance(package.get("review_gate"), dict) or not package.get("review_gate"):
            blockers.append("executor_review_package_gate_missing")
        return blockers

    @classmethod
    def _warnings(cls, selection: dict[str, Any], debugger_candidate_selection: dict[str, Any], selected_review: dict[str, Any], package: dict[str, Any], hook_candidate_selection: dict[str, Any] | None = None) -> list[str]:
        hook_candidate_selection = hook_candidate_selection or {}
        warnings: list[str] = []
        warnings.extend(f"source_map_followthrough_surface_selection:{item}" for item in cls._string_list(selection.get("warnings")))
        warnings.extend(f"source_map_debugger_candidate_selection:{item}" for item in cls._string_list(debugger_candidate_selection.get("warnings")))
        warnings.extend(f"source_map_hook_candidate_selection:{item}" for item in cls._string_list(hook_candidate_selection.get("warnings")))
        if debugger_candidate_selection:
            warnings.append("selected_executor_input_review_from_debugger_candidate_selection")
        if hook_candidate_selection:
            warnings.append("selected_executor_input_review_from_hook_candidate_selection")
        if selected_review:
            warnings.append("selected_source_map_executor_input_requires_explicit_review")
        if package:
            warnings.append("selected_executor_input_review_does_not_execute_surface")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], package: dict[str, Any], consumer: str) -> str:
        if any(item.startswith("source_map_debugger_candidate_selection") for item in blockers):
            return "provide_ready_source_map_debugger_candidate_selection_descriptor"
        if any(item.startswith("source_map_hook_candidate_selection") for item in blockers):
            return "provide_ready_source_map_hook_candidate_selection_descriptor"
        if "source_map_followthrough_surface_selection_missing" in blockers:
            return "provide_ready_source_map_followthrough_surface_selection_descriptor"
        if (
            "source_map_followthrough_surface_selection_not_ready" in blockers
            or "source_map_followthrough_surface_selection_not_ready_for_executor_review" in blockers
            or any(item.startswith("source_map_followthrough_surface_selection") for item in blockers)
        ):
            return "resolve_source_map_followthrough_surface_selection_blockers"
        if "selected_followthrough_review_missing" in blockers or "selected_executor_input_missing" in blockers:
            return "provide_selected_followthrough_review_and_executor_input"
        if any(item.endswith("_mismatch") for item in blockers) or "selected_consumer_unsupported" in blockers:
            return "refresh_selected_source_map_followthrough_surface"
        if blockers:
            return "fix_selected_source_map_executor_input_before_review"
        if package:
            return str((package.get("review_gate") or {}).get("next_action") or package.get("next_action") or "review_selected_source_map_executor_input")
        return "provide_ready_source_map_followthrough_surface_selection_descriptor"

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "preflight_only": True,
            "executor_input_review_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapSelectedExecutorApprovalPlanSpec:
    """Review-only approval/apply-plan for a selected Source Map executor input.

    This consumes the Step 274 selected executor-input review descriptor and
    prepares reviewer approval requirements plus a future apply input contract.
    It records no approval and invokes no executor.
    """

    source_map_selected_executor_input_review: dict[str, Any] = field(default_factory=dict)
    executor_review_package: dict[str, Any] = field(default_factory=dict)
    expected_action_id: str = ""
    expected_consumer: str = ""
    expected_gate: str = ""
    reviewer: str = ""
    approval_intent: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapSelectedExecutorApprovalPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_selected_executor_approval_plan",
                "sourceMapSelectedExecutorApprovalPlan",
                "source_map_selected_executor_apply_plan",
                "sourceMapSelectedExecutorApplyPlan",
                "source_map_followthrough_approval_plan",
                "sourceMapFollowthroughApprovalPlan",
            )
        )
        input_review = cls._object_alias(
            context,
            "source_map_selected_executor_input_review",
            "source-map-selected-executor-input-review",
            "sourceMapSelectedExecutorInputReview",
            "source_map_followthrough_executor_input_review",
            "source-map-followthrough-executor-input-review",
            "sourceMapFollowthroughExecutorInputReview",
            "source_map_selected_followthrough_review",
            "source-map-selected-followthrough-review",
            "sourceMapSelectedFollowthroughReview",
        )
        package = cls._object_alias(
            context,
            "executor_review_package",
            "executorReviewPackage",
            "source_map_executor_review_package",
            "sourceMapExecutorReviewPackage",
            "selected_executor_review_package",
            "selectedExecutorReviewPackage",
        )
        if not package and input_review:
            value = input_review.get("executor_review_package")
            package = value if isinstance(value, dict) else {}
        if not requested and not input_review and not package:
            return None
        return cls(
            source_map_selected_executor_input_review=input_review,
            executor_review_package=package,
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_gate=str(context.get("expected_gate", context.get("expectedGate", context.get("source_map_selected_executor_gate", context.get("sourceMapSelectedExecutorGate", "")))) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
            approval_intent=bool(context.get("approval_intent") or context.get("approvalIntent") or context.get("plan_approval") or context.get("planApproval")),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapSelectedExecutorApprovalPlanResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapSelectedExecutorApprovalPlanManager:
    """Plan explicit approval/apply gates for one selected Source Map executor."""

    def review(self, spec: SourceMapSelectedExecutorApprovalPlanSpec | None) -> SourceMapSelectedExecutorApprovalPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapSelectedExecutorApprovalPlanResult(status="unsupported", reason="missing_source_map_selected_executor_approval_plan_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapSelectedExecutorApprovalPlanResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_selected_executor_approval_plan_failed")
            descriptor["error"] = str(exc)
            return SourceMapSelectedExecutorApprovalPlanResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_selected_executor_approval_plan_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapSelectedExecutorApprovalPlanSpec) -> dict[str, Any]:
        input_review = spec.source_map_selected_executor_input_review
        package = dict(spec.executor_review_package) if isinstance(spec.executor_review_package, dict) else {}
        blockers = self._input_blockers(input_review, package)
        blockers.extend(self._expectation_blockers(spec, package))
        if package:
            blockers.extend(self._package_blockers(package))
        approval = {} if blockers else self._approval_requirements(package, spec)
        apply_plan = {} if blockers else self._apply_plan(package, approval)
        blockers.extend(self._approval_plan_blockers(approval, apply_plan))
        warnings = self._warnings(input_review, package, approval, apply_plan)
        status = "blocked" if blockers else "ready_for_review"
        gate = package.get("review_gate") if isinstance(package.get("review_gate"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-approval-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "approval_plan_only": True,
            "apply_plan_only": True,
            "handoff_only": True,
            "source_executor_input_review_schema_version": str(input_review.get("schema_version") or ""),
            "source_executor_input_review_status": self._status(input_review),
            "selected_action_id": str(package.get("action_id") or input_review.get("selected_action_id") or ""),
            "selected_consumer": str(package.get("consumer") or input_review.get("selected_consumer") or ""),
            "selected_followthrough_review_surface": str(package.get("followthrough_review_surface") or input_review.get("selected_followthrough_review_surface") or ""),
            "selected_review_gate": str(gate.get("gate") or ""),
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "expected_gate": spec.expected_gate,
            "reviewer": spec.reviewer,
            "approval_intent": spec.approval_intent,
            "executor_review_package": package,
            "approval_requirements": approval,
            "apply_plan": apply_plan,
            "approval_plan_ready": bool(approval) and not blockers,
            "apply_plan_ready_for_review": bool(apply_plan) and not blockers,
            "approval_recorded": False,
            "ready_to_apply_now": False,
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, package, approval, apply_plan),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-approval-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "approval_plan_only": True,
            "apply_plan_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_executor_input_review_schema_version": "",
            "source_executor_input_review_status": "",
            "selected_action_id": "",
            "selected_consumer": "",
            "selected_followthrough_review_surface": "",
            "selected_review_gate": "",
            "expected_action_id": "",
            "expected_consumer": "",
            "expected_gate": "",
            "reviewer": "",
            "approval_intent": False,
            "executor_review_package": {},
            "approval_requirements": {},
            "apply_plan": {},
            "approval_plan_ready": False,
            "apply_plan_ready_for_review": False,
            "approval_recorded": False,
            "ready_to_apply_now": False,
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_selected_executor_input_review_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, input_review: dict[str, Any], package: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not input_review and not package:
            blockers.append("source_map_selected_executor_input_review_missing")
        if input_review:
            if input_review.get("schema_version") not in {None, "", "reverse-deepagent.source-map-selected-executor-input-review.v1"}:
                blockers.append("source_map_selected_executor_input_review_schema_mismatch")
            if cls._status(input_review) in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_selected_executor_input_review_not_ready")
            if input_review.get("ready_for_executor_review") is not True:
                blockers.append("source_map_selected_executor_input_review_not_ready_for_approval_plan")
            if input_review.get("surface_executor_invoked") is True:
                blockers.append("source_map_selected_executor_input_review_executor_invoked")
            blockers.extend(f"source_map_selected_executor_input_review:{item}" for item in cls._string_list(input_review.get("blockers")))
            policy = input_review.get("side_effect_policy") if isinstance(input_review.get("side_effect_policy"), dict) else {}
            blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_selected_executor_input_review"))
        if not package:
            blockers.append("executor_review_package_missing")
        return blockers

    @staticmethod
    def _expectation_blockers(spec: SourceMapSelectedExecutorApprovalPlanSpec, package: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        gate = package.get("review_gate") if isinstance(package.get("review_gate"), dict) else {}
        action_id = str(package.get("action_id") or "")
        consumer = str(package.get("consumer") or "")
        gate_name = str(gate.get("gate") or "")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_consumer and consumer and spec.expected_consumer != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_gate and gate_name and spec.expected_gate != gate_name:
            blockers.append("selected_review_gate_mismatch")
        return blockers

    @classmethod
    def _package_blockers(cls, package: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        consumer = str(package.get("consumer") or "")
        gate = package.get("review_gate") if isinstance(package.get("review_gate"), dict) else {}
        executor_input = package.get("executor_input") if isinstance(package.get("executor_input"), dict) else {}
        if package.get("package_version") not in {None, "", "reverse-deepagent.source-map-selected-executor-input-review.package.v1"}:
            blockers.append("executor_review_package_version_mismatch")
        if package.get("requires_explicit_review") is not True:
            blockers.append("executor_review_package_explicit_review_missing")
        if package.get("ready_for_downstream_review") is not True:
            blockers.append("executor_review_package_not_ready")
        if package.get("execute_automatically") is True or package.get("executor_invoked") is True:
            blockers.append("executor_review_package_execution_claim_detected")
        blockers.extend(cls._side_effect_blockers(package.get("side_effect_policy") if isinstance(package.get("side_effect_policy"), dict) else {}, prefix="executor_review_package"))
        if consumer not in {"debugger", "source-logpoint", "rebuild", "hook"}:
            blockers.append("executor_review_package_consumer_unsupported")
        if not gate:
            blockers.append("executor_review_package_gate_missing")
        if gate.get("required_approval_flag") != "review_approved":
            blockers.append("executor_review_package_approval_flag_mismatch")
        if not executor_input:
            blockers.append("executor_review_package_input_missing")
        return blockers

    @staticmethod
    def _approval_requirements(package: dict[str, Any], spec: SourceMapSelectedExecutorApprovalPlanSpec) -> dict[str, Any]:
        gate = package.get("review_gate") if isinstance(package.get("review_gate"), dict) else {}
        consumer = str(package.get("consumer") or "")
        return {
            "approval_schema_version": "reverse-deepagent.source-map-selected-executor-approval.v1",
            "approval_required": True,
            "approval_recorded": False,
            "approval_intent_seen": spec.approval_intent,
            "reviewer_required": True,
            "reviewer": spec.reviewer,
            "required_approval_flag": str(gate.get("required_approval_flag") or "review_approved"),
            "approval_record_artifact": "workspace/source-map-selected-executor-approval-record.json",
            "approval_scope": {
                "action_id": str(package.get("action_id") or ""),
                "consumer": consumer,
                "review_gate": str(gate.get("gate") or ""),
            },
            "approval_next_action": f"record_review_approval_for_source_map_{consumer.replace('-', '_')}_executor" if consumer else "record_review_approval_for_source_map_executor",
        }

    @staticmethod
    def _apply_plan(package: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
        consumer = str(package.get("consumer") or "")
        gate = package.get("review_gate") if isinstance(package.get("review_gate"), dict) else {}
        executor_input = package.get("executor_input") if isinstance(package.get("executor_input"), dict) else {}
        future_actions = {
            "debugger": "execute_reviewed_source_map_debugger_location_action",
            "source-logpoint": "install_reviewed_source_map_source_logpoint",
            "rebuild": "run_reviewed_source_map_rebuild_metadata_generation",
            "hook": "install_reviewed_source_map_hook_symbol_scope",
        }
        result_artifacts = {
            "debugger": "workspace/source-map-debugger-execution-result.json",
            "source-logpoint": "workspace/source-map-source-logpoint-install-result.json",
            "rebuild": "workspace/source-map-rebuild-result.json",
            "hook": "workspace/source-map-hook-install-result.json",
        }
        return {
            "apply_plan_schema_version": "reverse-deepagent.source-map-selected-executor-apply-plan.v1",
            "consumer": consumer,
            "future_action": future_actions.get(consumer, "choose_supported_source_map_executor"),
            "review_gate": str(gate.get("gate") or ""),
            "executor_input": executor_input,
            "requires_approval_record": True,
            "required_approval_flag": approval.get("required_approval_flag", "review_approved"),
            "expected_approval_record_artifact": approval.get("approval_record_artifact", "workspace/source-map-selected-executor-approval-record.json"),
            "future_result_artifact": result_artifacts.get(consumer, "workspace/source-map-selected-executor-result.json"),
            "mode_required": "apply",
            "write_result_required": True,
            "ready_to_apply_now": False,
            "executor_implemented_now": False,
            "execute_automatically": False,
            "surface_executor_invoked": False,
            "side_effect_policy": SourceMapSelectedExecutorApprovalPlanManager._side_effect_policy(),
        }

    @classmethod
    def _approval_plan_blockers(cls, approval: dict[str, Any], apply_plan: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not approval or not apply_plan:
            return blockers
        if approval.get("approval_required") is not True:
            blockers.append("approval_requirement_missing")
        if approval.get("approval_recorded") is True:
            blockers.append("approval_plan_must_not_record_approval")
        if apply_plan.get("ready_to_apply_now") is True or apply_plan.get("surface_executor_invoked") is True:
            blockers.append("apply_plan_execution_claim_detected")
        blockers.extend(cls._side_effect_blockers(apply_plan.get("side_effect_policy") if isinstance(apply_plan.get("side_effect_policy"), dict) else {}, prefix="apply_plan"))
        return blockers

    @classmethod
    def _warnings(cls, input_review: dict[str, Any], package: dict[str, Any], approval: dict[str, Any], apply_plan: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        warnings.extend(f"source_map_selected_executor_input_review:{item}" for item in cls._string_list(input_review.get("warnings")))
        if package:
            warnings.append("source_map_selected_executor_requires_explicit_approval")
        if approval:
            warnings.append("approval_plan_does_not_record_approval")
        if apply_plan:
            warnings.append("apply_plan_does_not_execute_surface")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], package: dict[str, Any], approval: dict[str, Any], apply_plan: dict[str, Any]) -> str:
        if "source_map_selected_executor_input_review_missing" in blockers or "executor_review_package_missing" in blockers:
            return "provide_ready_source_map_selected_executor_input_review_descriptor"
        if any(item.startswith("source_map_selected_executor_input_review") for item in blockers):
            return "resolve_source_map_selected_executor_input_review_blockers"
        if any(item.endswith("_mismatch") for item in blockers) or "executor_review_package_consumer_unsupported" in blockers:
            return "refresh_source_map_selected_executor_input_review_package"
        if blockers:
            return "fix_source_map_selected_executor_approval_plan_inputs"
        if approval and apply_plan:
            return str(approval.get("approval_next_action") or "record_review_approval_for_source_map_executor")
        return "provide_ready_source_map_selected_executor_input_review_descriptor"

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "approval_plan_only": True,
            "apply_plan_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapSelectedExecutorApplyPreflightSpec:
    """Read-only apply preflight for a reviewed Source Map selected executor.

    This consumes the Step 275 approval/apply plan and the Step 276 explicit
    approval record. It verifies the selected executor scope, approval record,
    and digest gates before any future executor surface is considered. It never
    invokes debugger, source-logpoint, hook, rebuild, browser, CDP, MCP, or
    mobile runtime chains.
    """

    source_map_selected_executor_approval_plan: dict[str, Any] = field(default_factory=dict)
    source_map_selected_executor_approval_record: dict[str, Any] = field(default_factory=dict)
    source_map_followthrough_dispatcher_result: dict[str, Any] = field(default_factory=dict)
    expected_action_id: str = ""
    expected_consumer: str = ""
    expected_gate: str = ""
    expected_approval_record_id: str = ""
    expected_plan_digest_sha256: str = ""
    expected_dispatcher_result_id: str = ""
    expected_dispatcher_result_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapSelectedExecutorApplyPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_selected_executor_apply_preflight",
                "sourceMapSelectedExecutorApplyPreflight",
                "source_map_selected_executor_application_preflight",
                "sourceMapSelectedExecutorApplicationPreflight",
                "source_map_followthrough_apply_preflight",
                "sourceMapFollowthroughApplyPreflight",
            )
        )
        approval_plan = cls._object_alias(
            context,
            "source_map_selected_executor_approval_plan",
            "source-map-selected-executor-approval-plan",
            "sourceMapSelectedExecutorApprovalPlan",
            "source_map_selected_executor_apply_plan",
            "source-map-selected-executor-apply-plan",
            "sourceMapSelectedExecutorApplyPlan",
        )
        approval_record = cls._object_alias(
            context,
            "source_map_selected_executor_approval_record",
            "source-map-selected-executor-approval-record",
            "sourceMapSelectedExecutorApprovalRecord",
            "source_map_selected_executor_apply_approval_record",
            "source-map-selected-executor-apply-approval-record",
            "sourceMapSelectedExecutorApplyApprovalRecord",
        )
        dispatcher_result = cls._object_alias(
            context,
            "source_map_followthrough_dispatcher_result",
            "source-map-followthrough-dispatcher-result",
            "sourceMapFollowthroughDispatcherResult",
            "source_map_followthrough_dispatcher_mvp",
            "source-map-followthrough-dispatcher-mvp",
            "sourceMapFollowthroughDispatcherMvp",
            "source_map_followthrough_dispatch_next_action",
            "source-map-followthrough-dispatch-next-action",
            "sourceMapFollowthroughDispatchNextAction",
        )
        if not requested and not approval_plan and not approval_record and not dispatcher_result:
            return None
        return cls(
            source_map_selected_executor_approval_plan=approval_plan,
            source_map_selected_executor_approval_record=approval_record,
            source_map_followthrough_dispatcher_result=dispatcher_result,
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_gate=str(context.get("expected_gate", context.get("expectedGate", context.get("source_map_selected_executor_gate", context.get("sourceMapSelectedExecutorGate", "")))) or ""),
            expected_approval_record_id=str(context.get("expected_approval_record_id", context.get("expectedApprovalRecordId", "")) or ""),
            expected_plan_digest_sha256=str(context.get("expected_plan_digest_sha256", context.get("expectedPlanDigestSha256", "")) or ""),
            expected_dispatcher_result_id=str(context.get("expected_dispatcher_result_id", context.get("expectedDispatcherResultId", "")) or ""),
            expected_dispatcher_result_digest_sha256=str(context.get("expected_dispatcher_result_digest_sha256", context.get("expectedDispatcherResultDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapSelectedExecutorApplyPreflightResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapSelectedExecutorApplyPreflightManager:
    """Review the apply inputs after explicit Source Map executor approval."""

    def review(self, spec: SourceMapSelectedExecutorApplyPreflightSpec | None) -> SourceMapSelectedExecutorApplyPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapSelectedExecutorApplyPreflightResult(status="unsupported", reason="missing_source_map_selected_executor_apply_preflight_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapSelectedExecutorApplyPreflightResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_selected_executor_apply_preflight_failed")
            descriptor["error"] = str(exc)
            return SourceMapSelectedExecutorApplyPreflightResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_selected_executor_apply_preflight_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapSelectedExecutorApplyPreflightSpec) -> dict[str, Any]:
        approval_plan = spec.source_map_selected_executor_approval_plan
        approval_record = spec.source_map_selected_executor_approval_record
        dispatcher_result = spec.source_map_followthrough_dispatcher_result
        apply_plan = approval_plan.get("apply_plan") if isinstance(approval_plan.get("apply_plan"), dict) else {}
        package = approval_plan.get("executor_review_package") if isinstance(approval_plan.get("executor_review_package"), dict) else {}
        executor_input = apply_plan.get("executor_input") if isinstance(apply_plan.get("executor_input"), dict) else package.get("executor_input") if isinstance(package.get("executor_input"), dict) else {}
        blockers = self._input_blockers(approval_plan, approval_record, apply_plan, package)
        blockers.extend(self._expectation_blockers(spec, approval_plan, approval_record))
        blockers.extend(self._digest_blockers(spec, approval_plan, approval_record))
        blockers.extend(self._scope_blockers(approval_plan, approval_record, apply_plan, package))
        blockers.extend(self._executor_input_blockers(str(approval_plan.get("selected_consumer") or apply_plan.get("consumer") or ""), executor_input))
        consumer = str(approval_plan.get("selected_consumer") or apply_plan.get("consumer") or approval_record.get("selected_consumer") or "")
        action_id = str(approval_plan.get("selected_action_id") or approval_record.get("selected_action_id") or "")
        gate = str(approval_plan.get("selected_review_gate") or approval_record.get("selected_review_gate") or apply_plan.get("review_gate") or "")
        future_action = str(apply_plan.get("future_action") or self._future_action(consumer))
        future_result_artifact = str(apply_plan.get("future_result_artifact") or self._future_result_artifact(consumer))
        dispatcher_handoff = self._dispatcher_result_handoff(spec, dispatcher_result, consumer, future_result_artifact)
        dispatcher_result_blockers = self._dispatcher_result_blockers(spec, dispatcher_result, consumer, future_result_artifact, dispatcher_handoff)
        dispatcher_result_verified = bool(dispatcher_result) and not dispatcher_result_blockers
        if dispatcher_handoff:
            dispatcher_handoff = {**dispatcher_handoff, "dispatcher_result_verified": dispatcher_result_verified}
        blockers.extend(dispatcher_result_blockers)
        warnings = self._warnings(approval_plan, approval_record, apply_plan, dispatcher_result)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight.v1",
            "status": status,
            "review_only": True,
            "preflight_only": True,
            "apply_preflight_only": True,
            "handoff_only": True,
            "source_approval_plan_schema_version": str(approval_plan.get("schema_version") or ""),
            "source_approval_plan_status": self._status(approval_plan),
            "source_approval_record_schema_version": str(approval_record.get("schema_version") or ""),
            "source_approval_record_status": self._status(approval_record),
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_followthrough_review_surface": str(approval_plan.get("selected_followthrough_review_surface") or ""),
            "selected_review_gate": gate,
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "expected_gate": spec.expected_gate,
            "expected_approval_record_id": spec.expected_approval_record_id,
            "expected_plan_digest_sha256": spec.expected_plan_digest_sha256,
            "expected_dispatcher_result_id": spec.expected_dispatcher_result_id,
            "expected_dispatcher_result_digest_sha256": spec.expected_dispatcher_result_digest_sha256,
            "reviewer": spec.reviewer,
            "approval_record_id": str(approval_record.get("approval_record_id") or ""),
            "approval_plan_digest_sha256": self._stable_json_digest(approval_plan) if approval_plan else "",
            "approval_record_plan_digest_sha256": str(approval_record.get("approval_plan_digest_sha256") or ""),
            "source_dispatcher_result_schema_version": str(dispatcher_result.get("schema_version") or "") if dispatcher_result else "",
            "source_dispatcher_result_status": self._status(dispatcher_result) if dispatcher_result else "",
            "source_dispatcher_result_digest_sha256": self._stable_json_digest(dispatcher_result) if dispatcher_result else "",
            "dispatcher_result_id": str(dispatcher_result.get("dispatcher_result_id") or "") if dispatcher_result else "",
            "dispatcher_result_verified": dispatcher_result_verified,
            "dispatcher_result_optional": not bool(dispatcher_result),
            "dispatcher_decision_recorded": bool(dispatcher_result.get("dispatcher_decision_recorded") is True) if dispatcher_result else False,
            "dispatcher_result_handoff_only": True,
            "dispatcher_result_selected_executor_apply_preflight_invoked": False,
            "dispatcher_result_selected_executor_invoked": False,
            "dispatcher_result_dispatch_target_invoked": False,
            "dispatcher_result_handoff": dispatcher_handoff,
            "executor_review_package": package,
            "apply_plan": apply_plan,
            "executor_input": executor_input,
            "future_action": future_action,
            "future_result_artifact": future_result_artifact,
            "approval_record_verified": not blockers and bool(approval_record),
            "executor_input_ready": bool(executor_input) and not blockers,
            "ready_for_selected_executor_review": not blockers,
            "ready_to_apply_now": False,
            "future_executor_contract": {
                "implemented": False,
                "future_action": future_action,
                "requires_explicit_executor_approval": True,
                "requires_apply_mode": True,
                "requires_write_result": True,
                "requires_reviewed_apply_preflight": True,
            },
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, consumer),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight.v1",
            "status": status,
            "review_only": True,
            "preflight_only": True,
            "apply_preflight_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_approval_plan_schema_version": "",
            "source_approval_plan_status": "",
            "source_approval_record_schema_version": "",
            "source_approval_record_status": "",
            "selected_action_id": "",
            "selected_consumer": "",
            "selected_followthrough_review_surface": "",
            "selected_review_gate": "",
            "expected_action_id": "",
            "expected_consumer": "",
            "expected_gate": "",
            "expected_approval_record_id": "",
            "expected_plan_digest_sha256": "",
            "expected_dispatcher_result_id": "",
            "expected_dispatcher_result_digest_sha256": "",
            "reviewer": "",
            "approval_record_id": "",
            "approval_plan_digest_sha256": "",
            "approval_record_plan_digest_sha256": "",
            "source_dispatcher_result_schema_version": "",
            "source_dispatcher_result_status": "",
            "source_dispatcher_result_digest_sha256": "",
            "dispatcher_result_id": "",
            "dispatcher_result_verified": False,
            "dispatcher_result_optional": True,
            "dispatcher_decision_recorded": False,
            "dispatcher_result_handoff_only": True,
            "dispatcher_result_selected_executor_apply_preflight_invoked": False,
            "dispatcher_result_selected_executor_invoked": False,
            "dispatcher_result_dispatch_target_invoked": False,
            "dispatcher_result_handoff": {},
            "executor_review_package": {},
            "apply_plan": {},
            "executor_input": {},
            "future_action": "",
            "future_result_artifact": "",
            "approval_record_verified": False,
            "executor_input_ready": False,
            "ready_for_selected_executor_review": False,
            "ready_to_apply_now": False,
            "future_executor_contract": {"implemented": False},
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_selected_executor_approval_plan_and_record",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _input_blockers(cls, approval_plan: dict[str, Any], approval_record: dict[str, Any], apply_plan: dict[str, Any], package: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not approval_plan:
            blockers.append("source_map_selected_executor_approval_plan_missing")
        else:
            if approval_plan.get("schema_version") not in {None, "", "reverse-deepagent.source-map-selected-executor-approval-plan.v1"}:
                blockers.append("source_map_selected_executor_approval_plan_schema_mismatch")
            if cls._status(approval_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_selected_executor_approval_plan_not_ready")
            if approval_plan.get("approval_plan_ready") is not True:
                blockers.append("source_map_selected_executor_approval_plan_not_ready_for_apply_preflight")
            if approval_plan.get("apply_plan_ready_for_review") is not True:
                blockers.append("source_map_selected_executor_apply_plan_not_ready_for_preflight")
            if approval_plan.get("surface_executor_invoked") is True or approval_plan.get("ready_to_apply_now") is True:
                blockers.append("source_map_selected_executor_approval_plan_execution_claim_detected")
            blockers.extend(f"source_map_selected_executor_approval_plan:{item}" for item in cls._string_list(approval_plan.get("blockers")))
            blockers.extend(cls._side_effect_blockers(approval_plan.get("side_effect_policy") if isinstance(approval_plan.get("side_effect_policy"), dict) else {}, prefix="source_map_selected_executor_approval_plan"))
        if not approval_record:
            blockers.append("source_map_selected_executor_approval_record_missing")
        else:
            if approval_record.get("schema_version") not in {None, "", "reverse-deepagent.source-map-selected-executor-approval-record.v1"}:
                blockers.append("source_map_selected_executor_approval_record_schema_mismatch")
            if cls._status(approval_record) != "written":
                blockers.append("source_map_selected_executor_approval_record_not_written")
            if approval_record.get("approval_recorded") is not True:
                blockers.append("source_map_selected_executor_approval_record_not_recorded")
            if approval_record.get("approved_for_apply") is not True or approval_record.get("decision") != "approved":
                blockers.append("source_map_selected_executor_approval_record_not_approved")
            blockers.extend(f"source_map_selected_executor_approval_record:{item}" for item in cls._string_list(approval_record.get("blockers")))
            blockers.extend(cls._side_effect_blockers(approval_record.get("side_effect_policy") if isinstance(approval_record.get("side_effect_policy"), dict) else {}, prefix="source_map_selected_executor_approval_record"))
        if not apply_plan:
            blockers.append("source_map_selected_executor_apply_plan_missing")
        else:
            if apply_plan.get("apply_plan_schema_version") not in {None, "", "reverse-deepagent.source-map-selected-executor-apply-plan.v1"}:
                blockers.append("source_map_selected_executor_apply_plan_schema_mismatch")
            if apply_plan.get("requires_approval_record") is not True:
                blockers.append("source_map_selected_executor_apply_plan_approval_record_not_required")
            if apply_plan.get("ready_to_apply_now") is True or apply_plan.get("surface_executor_invoked") is True:
                blockers.append("source_map_selected_executor_apply_plan_execution_claim_detected")
            blockers.extend(cls._side_effect_blockers(apply_plan.get("side_effect_policy") if isinstance(apply_plan.get("side_effect_policy"), dict) else {}, prefix="source_map_selected_executor_apply_plan"))
        if not package:
            blockers.append("executor_review_package_missing")
        return blockers

    @staticmethod
    def _expectation_blockers(spec: SourceMapSelectedExecutorApplyPreflightSpec, approval_plan: dict[str, Any], approval_record: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        action_id = str(approval_plan.get("selected_action_id") or approval_record.get("selected_action_id") or "")
        consumer = str(approval_plan.get("selected_consumer") or approval_record.get("selected_consumer") or "")
        gate = str(approval_plan.get("selected_review_gate") or approval_record.get("selected_review_gate") or "")
        record_id = str(approval_record.get("approval_record_id") or "")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_consumer and consumer and spec.expected_consumer != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_gate and gate and spec.expected_gate != gate:
            blockers.append("selected_review_gate_mismatch")
        if spec.expected_approval_record_id and record_id and spec.expected_approval_record_id != record_id:
            blockers.append("approval_record_id_mismatch")
        return blockers

    @classmethod
    def _digest_blockers(cls, spec: SourceMapSelectedExecutorApplyPreflightSpec, approval_plan: dict[str, Any], approval_record: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not approval_plan or not approval_record:
            return blockers
        plan_digest = cls._stable_json_digest(approval_plan)
        record_digest = str(approval_record.get("approval_plan_digest_sha256") or "")
        if not record_digest:
            blockers.append("approval_record_plan_digest_missing")
        elif record_digest != plan_digest:
            blockers.append("approval_record_plan_digest_mismatch")
        if spec.expected_plan_digest_sha256 and spec.expected_plan_digest_sha256 != plan_digest:
            blockers.append("expected_plan_digest_mismatch")
        return blockers

    @staticmethod
    def _scope_blockers(approval_plan: dict[str, Any], approval_record: dict[str, Any], apply_plan: dict[str, Any], package: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        action_id = str(approval_plan.get("selected_action_id") or "")
        consumer = str(approval_plan.get("selected_consumer") or "")
        gate = str(approval_plan.get("selected_review_gate") or "")
        if approval_record:
            if str(approval_record.get("selected_action_id") or "") != action_id:
                blockers.append("approval_record_action_id_mismatch")
            if str(approval_record.get("selected_consumer") or "") != consumer:
                blockers.append("approval_record_consumer_mismatch")
            if str(approval_record.get("selected_review_gate") or "") != gate:
                blockers.append("approval_record_gate_mismatch")
        if apply_plan:
            if str(apply_plan.get("consumer") or "") != consumer:
                blockers.append("apply_plan_consumer_mismatch")
            if str(apply_plan.get("review_gate") or "") != gate:
                blockers.append("apply_plan_gate_mismatch")
        if package:
            if str(package.get("action_id") or "") != action_id:
                blockers.append("executor_review_package_action_id_mismatch")
            if str(package.get("consumer") or "") != consumer:
                blockers.append("executor_review_package_consumer_mismatch")
        return blockers

    @staticmethod
    def _executor_input_blockers(consumer: str, executor_input: dict[str, Any]) -> list[str]:
        if consumer == "debugger":
            return SourceMapTypedPayloadPreflightManager._debugger_blockers("debugger-location-review", executor_input)
        if consumer == "source-logpoint":
            return SourceMapTypedPayloadPreflightManager._source_logpoint_blockers("source-logpoint-plan-review", executor_input)
        if consumer == "rebuild":
            return SourceMapTypedPayloadPreflightManager._rebuild_blockers("rebuild-source-metadata-review", executor_input)
        if consumer == "hook":
            return SourceMapTypedPayloadPreflightManager._hook_blockers("hook-symbol-scope-review", executor_input)
        return ["selected_consumer_unsupported"] if consumer else []

    @classmethod
    def _dispatcher_result_blockers(
        cls,
        spec: SourceMapSelectedExecutorApplyPreflightSpec,
        dispatcher_result: dict[str, Any],
        consumer: str,
        future_result_artifact: str,
        dispatcher_handoff: dict[str, Any],
    ) -> list[str]:
        if not dispatcher_result:
            return []
        blockers: list[str] = []
        if dispatcher_result.get("schema_version") not in {None, "", "reverse-deepagent.source-map-followthrough-dispatcher-result.v1"}:
            blockers.append("source_map_followthrough_dispatcher_result_schema_mismatch")
        if cls._status(dispatcher_result) != "dispatched":
            blockers.append("source_map_followthrough_dispatcher_result_not_dispatched")
        if dispatcher_result.get("dispatcher_decision_recorded") is not True:
            blockers.append("source_map_followthrough_dispatcher_result_decision_missing")
        if dispatcher_result.get("requires_selected_executor_apply_preflight") is not True:
            blockers.append("source_map_followthrough_dispatcher_result_apply_preflight_not_required")
        if dispatcher_result.get("selected_executor_invoked") is True or dispatcher_result.get("executor_invoked") is True:
            blockers.append("source_map_followthrough_dispatcher_result_selected_executor_already_invoked")
        if dispatcher_result.get("selected_executor_apply_preflight_invoked") is True:
            blockers.append("source_map_followthrough_dispatcher_result_apply_preflight_already_invoked")
        if dispatcher_result.get("dispatch_target_invoked") is True or dispatcher_result.get("dispatcher_invoked") is True:
            blockers.append("source_map_followthrough_dispatcher_result_dispatch_target_already_invoked")
        if consumer and str(dispatcher_result.get("selected_consumer") or "") != consumer:
            blockers.append("source_map_followthrough_dispatcher_result_consumer_mismatch")
        required_artifact = str(dispatcher_result.get("required_result_artifact") or "")
        if future_result_artifact and required_artifact and required_artifact != future_result_artifact:
            blockers.append("source_map_followthrough_dispatcher_result_required_artifact_mismatch")
        result_id = str(dispatcher_result.get("dispatcher_result_id") or "")
        if spec.expected_dispatcher_result_id and result_id and spec.expected_dispatcher_result_id != result_id:
            blockers.append("source_map_followthrough_dispatcher_result_id_mismatch")
        result_digest = dispatcher_handoff.get("source_dispatcher_result_digest_sha256", "")
        if spec.expected_dispatcher_result_digest_sha256 and spec.expected_dispatcher_result_digest_sha256 != result_digest:
            blockers.append("source_map_followthrough_dispatcher_result_digest_mismatch")
        policy = dispatcher_result.get("side_effect_policy") if isinstance(dispatcher_result.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._dispatcher_result_side_effect_blockers(dispatcher_result, policy))
        blockers.extend(f"source_map_followthrough_dispatcher_result:{item}" for item in cls._string_list(dispatcher_result.get("blockers")))
        return blockers

    @classmethod
    def _dispatcher_result_handoff(
        cls,
        spec: SourceMapSelectedExecutorApplyPreflightSpec,
        dispatcher_result: dict[str, Any],
        consumer: str,
        future_result_artifact: str,
    ) -> dict[str, Any]:
        if not dispatcher_result:
            return {
                "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight-dispatcher-result-handoff.v1",
                "provided": False,
                "optional": True,
                "dispatcher_result_verified": False,
                "selected_consumer": consumer,
                "selected_executor_apply_preflight_artifact": "workspace/source-map-selected-executor-apply-preflight.json",
            }
        digest = cls._stable_json_digest(dispatcher_result)
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight-dispatcher-result-handoff.v1",
            "provided": True,
            "optional": False,
            "dispatcher_result_id": str(dispatcher_result.get("dispatcher_result_id") or ""),
            "source_dispatcher_result_schema_version": str(dispatcher_result.get("schema_version") or ""),
            "source_dispatcher_result_status": cls._status(dispatcher_result),
            "source_dispatcher_result_digest_sha256": digest,
            "expected_dispatcher_result_id": spec.expected_dispatcher_result_id,
            "expected_dispatcher_result_digest_sha256": spec.expected_dispatcher_result_digest_sha256,
            "dispatcher_result_verified": False,
            "dispatcher_decision_recorded": dispatcher_result.get("dispatcher_decision_recorded") is True,
            "requires_selected_executor_apply_preflight": dispatcher_result.get("requires_selected_executor_apply_preflight") is True,
            "selected_consumer": consumer,
            "dispatcher_result_selected_consumer": str(dispatcher_result.get("selected_consumer") or ""),
            "dispatch_surface": str(dispatcher_result.get("dispatch_surface") or ""),
            "required_result_artifact": str(dispatcher_result.get("required_result_artifact") or ""),
            "future_result_artifact": future_result_artifact,
            "selected_executor_apply_preflight_artifact": "workspace/source-map-selected-executor-apply-preflight.json",
            "selected_executor_apply_preflight_invoked": False,
            "selected_executor_invoked": False,
            "dispatch_target_invoked": False,
            "handoff_only": True,
        }

    @staticmethod
    def _dispatcher_result_side_effect_blockers(dispatcher_result: dict[str, Any], policy: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        forbidden = (
            "ready_to_dispatch_now",
            "ready_to_execute_now",
            "ready_to_execute_selected_executor_now",
            "dispatcher_invoked",
            "dispatch_target_invoked",
            "executor_invoked",
            "selected_executor_invoked",
            "selected_executor_apply_preflight_invoked",
            "runtime_apply_preflight_invoked",
            "debugger_execution_performed",
            "runtime_evaluated",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "fetch_source_map",
            "source_map_fetched",
            "browser_started",
            "cdp_command_sent",
            "calls_mcp",
            "mobile_runtime_used",
        )
        for key in forbidden:
            if dispatcher_result.get(key) is True or policy.get(key) is True:
                blockers.append("source_map_followthrough_dispatcher_result_side_effect_detected")
                break
        return blockers

    @classmethod
    def _warnings(cls, approval_plan: dict[str, Any], approval_record: dict[str, Any], apply_plan: dict[str, Any], dispatcher_result: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        warnings.extend(f"source_map_selected_executor_approval_plan:{item}" for item in cls._string_list(approval_plan.get("warnings")))
        if approval_record:
            warnings.append("source_map_selected_executor_approval_record_requires_apply_preflight_review")
        if apply_plan:
            warnings.append("source_map_selected_executor_apply_preflight_does_not_execute_surface")
        if dispatcher_result:
            warnings.append("source_map_followthrough_dispatcher_result_handoff_does_not_execute_selected_executor")
            warnings.append("source_map_followthrough_dispatcher_result_verified_for_apply_preflight_only")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], consumer: str) -> str:
        if "source_map_selected_executor_approval_plan_missing" in blockers or "source_map_selected_executor_approval_record_missing" in blockers:
            return "provide_source_map_selected_executor_approval_plan_and_record"
        if any(item.startswith("source_map_selected_executor_approval_plan") for item in blockers):
            return "resolve_source_map_selected_executor_approval_plan_blockers"
        if any(item.startswith("source_map_selected_executor_approval_record") or item.startswith("approval_record") for item in blockers):
            return "record_or_refresh_source_map_selected_executor_approval"
        if any(item.startswith("source_map_followthrough_dispatcher_result") for item in blockers):
            return "resolve_source_map_followthrough_dispatcher_result_handoff_blockers"
        if any(item.endswith("_mismatch") for item in blockers):
            return "refresh_matching_source_map_selected_executor_approval_inputs"
        if blockers:
            return "fix_source_map_selected_executor_apply_preflight_inputs"
        return f"review_source_map_{consumer.replace('-', '_')}_executor_application" if consumer else "review_source_map_selected_executor_application"

    @staticmethod
    def _future_action(consumer: str) -> str:
        return {
            "debugger": "execute_reviewed_source_map_debugger_location_action",
            "source-logpoint": "install_reviewed_source_map_source_logpoint",
            "rebuild": "run_reviewed_source_map_rebuild_metadata_generation",
            "hook": "install_reviewed_source_map_hook_symbol_scope",
        }.get(consumer, "choose_supported_source_map_executor")

    @staticmethod
    def _future_result_artifact(consumer: str) -> str:
        return {
            "debugger": "workspace/source-map-debugger-execution-result.json",
            "source-logpoint": "workspace/source-map-source-logpoint-install-result.json",
            "rebuild": "workspace/source-map-rebuild-result.json",
            "hook": "workspace/source-map-hook-install-result.json",
        }.get(consumer, "workspace/source-map-selected-executor-result.json")

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "apply_preflight_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapSelectedExecutorApplicationHandoffSpec:
    """Review-only handoff from a ready selected-executor apply preflight to its application surface.

    This descriptor turns the Step 277 / Step 300 apply-preflight evidence into
    a machine-readable application review input package for the existing
    debugger / source-logpoint / hook / rebuild explicit application routes. It
    never invokes those routes and never starts browsers, sends CDP commands,
    evaluates JavaScript, installs hooks / logpoints, runs rebuilds, calls MCP,
    or touches mobile runtime chains.
    """

    source_map_selected_executor_apply_preflight: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_apply_preflight_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapSelectedExecutorApplicationHandoffSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_selected_executor_application_handoff",
                "sourceMapSelectedExecutorApplicationHandoff",
                "source_map_selected_executor_application_review_input",
                "sourceMapSelectedExecutorApplicationReviewInput",
                "source_map_followthrough_application_handoff",
                "sourceMapFollowthroughApplicationHandoff",
            )
        )
        apply_preflight = cls._object_alias(
            context,
            "source_map_selected_executor_apply_preflight",
            "source-map-selected-executor-apply-preflight",
            "sourceMapSelectedExecutorApplyPreflight",
            "source_map_selected_executor_application_preflight",
            "source-map-selected-executor-application-preflight",
            "sourceMapSelectedExecutorApplicationPreflight",
        )
        if not requested and not apply_preflight:
            return None
        return cls(
            source_map_selected_executor_apply_preflight=apply_preflight,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_apply_preflight_digest_sha256=str(context.get("expected_apply_preflight_digest_sha256", context.get("expectedApplyPreflightDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapSelectedExecutorApplicationHandoffResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapSelectedExecutorApplicationHandoffManager:
    """Build a review-only selected executor application handoff descriptor."""

    _SURFACES: dict[str, dict[str, Any]] = {
        "debugger": {
            "application_surface": "source-map-debugger-application",
            "review_action": "review_source_map_debugger_executor_application",
            "future_action": "execute_reviewed_source_map_debugger_location_action",
            "result_artifact": "workspace/source-map-debugger-execution-result.json",
            "review_gate": "explicit_debugger_location_review",
            "application_input_key": "source_map_debugger_location_input",
            "approval_flags": ("review_approved", "approve_source_map_debugger_action"),
            "next_action": "review_source_map_debugger_executor_application",
        },
        "source-logpoint": {
            "application_surface": "source-map-source-logpoint-application",
            "review_action": "review_source_map_source_logpoint_executor_application",
            "future_action": "install_reviewed_source_map_source_logpoint",
            "result_artifact": "workspace/source-map-source-logpoint-install-result.json",
            "review_gate": "explicit_source_logpoint_install_review",
            "application_input_key": "source_map_source_logpoint_install_input",
            "approval_flags": ("review_approved", "approve_source_logpoint_install"),
            "next_action": "review_source_map_source_logpoint_executor_application",
        },
        "hook": {
            "application_surface": "source-map-hook-application",
            "review_action": "review_source_map_hook_executor_application",
            "future_action": "install_reviewed_source_map_hook_symbol_scope",
            "result_artifact": "workspace/source-map-hook-install-result.json",
            "review_gate": "explicit_hook_symbol_scope_review",
            "application_input_key": "source_map_hook_install_input",
            "approval_flags": ("review_approved", "approve_source_map_hook_install"),
            "next_action": "review_source_map_hook_executor_application",
        },
        "rebuild": {
            "application_surface": "source-map-rebuild-metadata-application",
            "review_action": "review_source_map_rebuild_executor_application",
            "future_action": "run_reviewed_source_map_rebuild_metadata_generation",
            "result_artifact": "workspace/source-map-rebuild-result.json",
            "review_gate": "explicit_rebuild_source_metadata_review",
            "application_input_key": "source_map_rebuild_metadata_input",
            "approval_flags": ("review_approved", "approve_source_map_rebuild_metadata"),
            "next_action": "review_source_map_rebuild_executor_application",
        },
    }

    def review(self, spec: SourceMapSelectedExecutorApplicationHandoffSpec | None) -> SourceMapSelectedExecutorApplicationHandoffResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapSelectedExecutorApplicationHandoffResult(status="unsupported", reason="missing_source_map_selected_executor_application_handoff_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapSelectedExecutorApplicationHandoffResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_selected_executor_application_handoff_failed")
            descriptor["error"] = str(exc)
            return SourceMapSelectedExecutorApplicationHandoffResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_selected_executor_application_handoff_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapSelectedExecutorApplicationHandoffSpec) -> dict[str, Any]:
        apply_preflight = spec.source_map_selected_executor_apply_preflight
        consumer = str(apply_preflight.get("selected_consumer") or "")
        action_id = str(apply_preflight.get("selected_action_id") or "")
        gate = str(apply_preflight.get("selected_review_gate") or "")
        surface = self._SURFACES.get(consumer, {})
        executor_input = apply_preflight.get("executor_input") if isinstance(apply_preflight.get("executor_input"), dict) else {}
        digest = self._stable_json_digest(apply_preflight) if apply_preflight else ""
        blockers = self._blockers(spec, apply_preflight, surface, executor_input, digest)
        status = "blocked" if blockers else "ready_for_review"
        result_artifact = str(apply_preflight.get("future_result_artifact") or surface.get("result_artifact") or "workspace/source-map-selected-executor-result.json")
        future_action = str(apply_preflight.get("future_action") or surface.get("future_action") or "")
        application_surface = str(surface.get("application_surface") or "")
        application_review_input = self._application_review_input(apply_preflight, surface, executor_input, digest, result_artifact, future_action)
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-application-handoff.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "handoff_only": True,
            "application_handoff_only": True,
            "selected_executor_application_handoff_only": True,
            "source_apply_preflight_schema_version": str(apply_preflight.get("schema_version") or "") if apply_preflight else "",
            "source_apply_preflight_status": self._status(apply_preflight),
            "source_apply_preflight_digest_sha256": digest,
            "expected_apply_preflight_digest_sha256": spec.expected_apply_preflight_digest_sha256,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": gate,
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer,
            "approval_record_id": str(apply_preflight.get("approval_record_id") or ""),
            "approval_record_verified": bool(apply_preflight.get("approval_record_verified") is True),
            "executor_input_ready": bool(apply_preflight.get("executor_input_ready") is True),
            "ready_for_selected_executor_review": bool(apply_preflight.get("ready_for_selected_executor_review") is True),
            "ready_for_application_review": not blockers,
            "ready_to_apply_now": False,
            "ready_to_execute_now": False,
            "application_surface": application_surface,
            "application_review_action": str(surface.get("review_action") or ""),
            "application_input_key": str(surface.get("application_input_key") or ""),
            "required_approval_flags": list(surface.get("approval_flags") or ()),
            "future_action": future_action,
            "future_result_artifact": result_artifact,
            "application_review_input": application_review_input,
            "executor_input": executor_input,
            "surface_executor_invoked": False,
            "application_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(apply_preflight),
            "next_action": self._next_action(blockers, consumer, surface),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-application-handoff.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "handoff_only": True,
            "application_handoff_only": True,
            "reason": reason,
            "selected_consumer": "",
            "application_surface": "",
            "application_review_action": "",
            "future_result_artifact": "",
            "application_review_input": {},
            "ready_for_application_review": False,
            "ready_to_execute_now": False,
            "surface_executor_invoked": False,
            "application_invoked": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_selected_executor_apply_preflight",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapSelectedExecutorApplicationHandoffSpec,
        apply_preflight: dict[str, Any],
        surface: dict[str, Any],
        executor_input: dict[str, Any],
        digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not apply_preflight:
            return ["source_map_selected_executor_apply_preflight_missing"]
        if apply_preflight.get("schema_version") != "reverse-deepagent.source-map-selected-executor-apply-preflight.v1":
            blockers.append("source_map_selected_executor_apply_preflight_schema_mismatch")
        if cls._status(apply_preflight) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_selected_executor_apply_preflight_not_ready")
        consumer = str(apply_preflight.get("selected_consumer") or "")
        action_id = str(apply_preflight.get("selected_action_id") or "")
        gate = str(apply_preflight.get("selected_review_gate") or "")
        if not surface:
            blockers.append("source_map_selected_executor_application_surface_unsupported")
        elif gate and gate != str(surface.get("review_gate") or ""):
            blockers.append("source_map_selected_executor_review_gate_mismatch")
        if spec.expected_consumer and consumer and spec.expected_consumer != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_apply_preflight_digest_sha256 and spec.expected_apply_preflight_digest_sha256 != digest:
            blockers.append("source_map_selected_executor_apply_preflight_digest_mismatch")
        if apply_preflight.get("approval_record_verified") is not True:
            blockers.append("source_map_selected_executor_approval_record_not_verified")
        if apply_preflight.get("executor_input_ready") is not True or apply_preflight.get("ready_for_selected_executor_review") is not True:
            blockers.append("source_map_selected_executor_apply_preflight_input_not_ready")
        if apply_preflight.get("ready_to_apply_now") is True or apply_preflight.get("surface_executor_invoked") is True:
            blockers.append("source_map_selected_executor_apply_preflight_execution_claim_detected")
        future = apply_preflight.get("future_executor_contract") if isinstance(apply_preflight.get("future_executor_contract"), dict) else {}
        if future.get("implemented") is not False:
            blockers.append("source_map_selected_executor_future_contract_unexpected")
        blockers.extend(cls._executor_input_blockers(consumer, executor_input))
        blockers.extend(cls._side_effect_blockers(apply_preflight.get("side_effect_policy") if isinstance(apply_preflight.get("side_effect_policy"), dict) else {}, prefix="source_map_selected_executor_apply_preflight"))
        return blockers

    @classmethod
    def _application_review_input(
        cls,
        apply_preflight: dict[str, Any],
        surface: dict[str, Any],
        executor_input: dict[str, Any],
        digest: str,
        result_artifact: str,
        future_action: str,
    ) -> dict[str, Any]:
        if not apply_preflight or not surface:
            return {}
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-application-review-input.v1",
            "application_surface": surface["application_surface"],
            "application_review_action": surface["review_action"],
            "application_input_key": surface["application_input_key"],
            "required_approval_flags": list(surface["approval_flags"]),
            "selected_action_id": str(apply_preflight.get("selected_action_id") or ""),
            "selected_consumer": str(apply_preflight.get("selected_consumer") or ""),
            "selected_review_gate": str(apply_preflight.get("selected_review_gate") or ""),
            "approval_record_id": str(apply_preflight.get("approval_record_id") or ""),
            "apply_preflight_digest_sha256": digest,
            "apply_preflight_artifact": "workspace/source-map-selected-executor-apply-preflight.json",
            "result_artifact": result_artifact,
            "future_action": future_action,
            "executor_input": executor_input,
            "required_context": {
                "mode": "apply",
                "review_approved": True,
                "reviewer": "<required>",
                "source_map_selected_executor_apply_preflight": "<ready descriptor>",
                surface["application_input_key"]: "<reviewed input>",
            },
            "execute_automatically": False,
            "ready_to_execute_now": False,
            "requires_explicit_review": True,
            "requires_apply_mode": True,
            "requires_write_result": True,
            "handoff_only": True,
            "surface_executor_invoked": False,
        }

    @classmethod
    def _warnings(cls, apply_preflight: dict[str, Any]) -> list[str]:
        warnings = ["source_map_selected_executor_application_handoff_does_not_execute_surface"]
        if apply_preflight:
            warnings.append("source_map_selected_executor_application_requires_explicit_application_review")
        return warnings

    @classmethod
    def _next_action(cls, blockers: list[str], consumer: str, surface: dict[str, Any]) -> str:
        if any(item.startswith("source_map_selected_executor_apply_preflight") or item.startswith("source_map_selected_executor_approval") for item in blockers):
            return "provide_ready_source_map_selected_executor_apply_preflight"
        if any(item.endswith("_mismatch") for item in blockers):
            return "refresh_matching_source_map_selected_executor_application_handoff_inputs"
        if blockers:
            return "resolve_source_map_selected_executor_application_handoff_blockers"
        return str(surface.get("next_action") or f"review_source_map_{consumer.replace('-', '_')}_executor_application")

    @staticmethod
    def _executor_input_blockers(consumer: str, executor_input: dict[str, Any]) -> list[str]:
        return SourceMapSelectedExecutorApplyPreflightManager._executor_input_blockers(consumer, executor_input)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)
    _string_list = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "handoff_only": True,
            "application_handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "application_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapSelectedExecutorResultCheckpointSpec:
    """Read-only checkpoint over an explicit selected-executor application result.

    This descriptor consumes one already-produced selected executor application
    result and optionally the Step 301 application handoff descriptor.  It does
    not invoke debugger / source-logpoint / hook / rebuild application routes,
    does not start browsers, does not send CDP commands, does not evaluate
    JavaScript, does not install hooks or logpoints, does not run rebuilds, and
    never calls MCP or mobile runtime chains.
    """

    source_map_selected_executor_application_result: dict[str, Any] = field(default_factory=dict)
    source_map_selected_executor_application_handoff: dict[str, Any] = field(default_factory=dict)
    source_map_rebuild_generation_result: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_application_result_digest_sha256: str = ""
    expected_application_handoff_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapSelectedExecutorResultCheckpointSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_selected_executor_result_checkpoint",
                "sourceMapSelectedExecutorResultCheckpoint",
                "source_map_selected_executor_application_result_checkpoint",
                "sourceMapSelectedExecutorApplicationResultCheckpoint",
                "source_map_followthrough_result_checkpoint",
                "sourceMapFollowthroughResultCheckpoint",
            )
        )
        application_result = cls._object_alias(
            context,
            "source_map_selected_executor_application_result",
            "source-map-selected-executor-application-result",
            "sourceMapSelectedExecutorApplicationResult",
            "source_map_debugger_execution_result",
            "source-map-debugger-execution-result",
            "sourceMapDebuggerExecutionResult",
            "source_map_source_logpoint_install_result",
            "source-map-source-logpoint-install-result",
            "sourceMapSourceLogpointInstallResult",
            "source_map_hook_install_result",
            "source-map-hook-install-result",
            "sourceMapHookInstallResult",
            "source_map_rebuild_result",
            "source-map-rebuild-result",
            "sourceMapRebuildResult",
        )
        handoff = cls._object_alias(
            context,
            "source_map_selected_executor_application_handoff",
            "source-map-selected-executor-application-handoff",
            "sourceMapSelectedExecutorApplicationHandoff",
            "source_map_selected_executor_application_review_input",
            "source-map-selected-executor-application-review-input",
            "sourceMapSelectedExecutorApplicationReviewInput",
        )
        rebuild_generation = cls._object_alias(
            context,
            "source_map_rebuild_generation_result",
            "source-map-rebuild-generation-result",
            "sourceMapRebuildGenerationResult",
        )
        if not requested and not application_result:
            return None
        return cls(
            source_map_selected_executor_application_result=application_result,
            source_map_selected_executor_application_handoff=handoff,
            source_map_rebuild_generation_result=rebuild_generation,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_application_result_digest_sha256=str(context.get("expected_application_result_digest_sha256", context.get("expectedApplicationResultDigestSha256", "")) or ""),
            expected_application_handoff_digest_sha256=str(context.get("expected_application_handoff_digest_sha256", context.get("expectedApplicationHandoffDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapSelectedExecutorResultCheckpointResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapSelectedExecutorResultCheckpointManager:
    """Review-only checkpoint for selected Source Map executor application results."""

    _SURFACES: dict[str, dict[str, Any]] = {
        "debugger": {
            "application_surface": "source-map-debugger-application",
            "result_schema": "reverse-deepagent.source-map-debugger-execution-result.v1",
            "result_artifact": "workspace/source-map-debugger-execution-result.json",
            "review_gate": "explicit_debugger_location_review",
            "approval_flag": "approve_source_map_debugger_action",
            "success_key": "debugger_location_applied",
            "result_kind": "debugger-location",
        },
        "source-logpoint": {
            "application_surface": "source-map-source-logpoint-application",
            "result_schema": "",
            "result_artifact": "workspace/source-map-source-logpoint-install-result.json",
            "review_gate": "explicit_source_logpoint_install_review",
            "approval_flag": "approve_source_logpoint_install",
            "success_key": "logpoint_installed",
            "result_kind": "source-logpoint-install",
        },
        "hook": {
            "application_surface": "source-map-hook-application",
            "result_schema": "reverse-deepagent.source-map-hook-install-result.v1",
            "result_artifact": "workspace/source-map-hook-install-result.json",
            "review_gate": "explicit_hook_symbol_scope_review",
            "approval_flag": "approve_source_map_hook_install",
            "success_key": "hook_installed",
            "result_kind": "hook-install",
        },
        "rebuild": {
            "application_surface": "source-map-rebuild-metadata-application",
            "result_schema": "reverse-deepagent.source-map-rebuild-result.v1",
            "result_artifact": "workspace/source-map-rebuild-result.json",
            "review_gate": "explicit_rebuild_source_metadata_review",
            "approval_flag": "approve_source_map_rebuild_metadata",
            "success_key": "rebuild_metadata_applied",
            "result_kind": "rebuild-metadata",
        },
    }

    def review(self, spec: SourceMapSelectedExecutorResultCheckpointSpec | None) -> SourceMapSelectedExecutorResultCheckpointResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapSelectedExecutorResultCheckpointResult(status="unsupported", reason="missing_source_map_selected_executor_result_checkpoint_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapSelectedExecutorResultCheckpointResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_selected_executor_result_checkpoint_failed")
            descriptor["error"] = str(exc)
            return SourceMapSelectedExecutorResultCheckpointResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_selected_executor_result_checkpoint_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapSelectedExecutorResultCheckpointSpec) -> dict[str, Any]:
        result = spec.source_map_selected_executor_application_result
        handoff = spec.source_map_selected_executor_application_handoff
        rebuild_generation = spec.source_map_rebuild_generation_result
        consumer = self._infer_consumer(result, handoff)
        surface = self._SURFACES.get(consumer, {})
        action_id = str(result.get("selected_action_id") or handoff.get("selected_action_id") or "") if result or handoff else ""
        gate = str(result.get("selected_review_gate") or handoff.get("selected_review_gate") or "") if result or handoff else ""
        result_digest = self._stable_json_digest(result) if result else ""
        handoff_digest = self._stable_json_digest(handoff) if handoff else ""
        generation_digest = self._stable_json_digest(rebuild_generation) if rebuild_generation else ""
        blockers = self._blockers(spec, result, handoff, rebuild_generation, surface, consumer, action_id, gate, result_digest, handoff_digest)
        status = "blocked" if blockers else "ready_for_review"
        observed_side_effects = self._observed_application_side_effects(result)
        checkpoint_review = self._checkpoint_review(surface, result, rebuild_generation, result_digest, generation_digest)
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1",
            "status": status,
            "review_only": True,
            "checkpoint_only": True,
            "application_result_checkpoint_only": True,
            "handoff_only": True,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": gate,
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer or str(result.get("reviewer") or ""),
            "application_surface": str(surface.get("application_surface") or handoff.get("application_surface") or ""),
            "application_result_artifact": str(surface.get("result_artifact") or handoff.get("future_result_artifact") or ""),
            "application_result_schema_version": str(result.get("schema_version") or ""),
            "application_result_status": self._status(result),
            "application_result_digest_sha256": result_digest,
            "expected_application_result_digest_sha256": spec.expected_application_result_digest_sha256,
            "source_application_handoff_schema_version": str(handoff.get("schema_version") or "") if handoff else "",
            "source_application_handoff_status": self._status(handoff),
            "source_application_handoff_digest_sha256": handoff_digest,
            "expected_application_handoff_digest_sha256": spec.expected_application_handoff_digest_sha256,
            "application_handoff_verified": bool(handoff) and not self._handoff_blockers(spec, result, handoff, surface, consumer, action_id, gate, handoff_digest),
            "application_result_verified": not blockers,
            "review_approved": bool(result.get("review_approved") is True),
            "mode": str(result.get("mode") or ""),
            "approval_record_id": str(result.get("approval_record_id") or handoff.get("approval_record_id") or ""),
            "surface_executor_invoked": bool(result.get("surface_executor_invoked") is True),
            "result_success_key": str(surface.get("success_key") or ""),
            "result_success": bool(result.get(str(surface.get("success_key") or "")) is True) if surface else False,
            "ready_for_followthrough_checkpoint_review": not blockers,
            "ready_for_next_explicit_review": not blockers,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked_by_checkpoint": False,
            "source_logpoint_install_invoked_by_checkpoint": False,
            "rebuild_invoked_by_checkpoint": False,
            "browser_started_by_checkpoint": False,
            "cdp_command_sent_by_checkpoint": False,
            "runtime_evaluated_by_checkpoint": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "observed_application_side_effects": observed_side_effects,
            "optional_rebuild_generation_result_schema_version": str(rebuild_generation.get("schema_version") or "") if rebuild_generation else "",
            "optional_rebuild_generation_result_status": self._status(rebuild_generation),
            "optional_rebuild_generation_result_digest_sha256": generation_digest,
            "checkpoint_review": checkpoint_review,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(result, rebuild_generation),
            "next_action": self._next_action(blockers, consumer, result, rebuild_generation),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1",
            "status": status,
            "review_only": True,
            "checkpoint_only": True,
            "application_result_checkpoint_only": True,
            "reason": reason,
            "selected_consumer": "",
            "application_surface": "",
            "application_result_artifact": "",
            "application_result_status": "",
            "application_result_verified": False,
            "ready_for_followthrough_checkpoint_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_selected_executor_application_result",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapSelectedExecutorResultCheckpointSpec,
        result: dict[str, Any],
        handoff: dict[str, Any],
        rebuild_generation: dict[str, Any],
        surface: dict[str, Any],
        consumer: str,
        action_id: str,
        gate: str,
        result_digest: str,
        handoff_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not result:
            return ["source_map_selected_executor_application_result_missing"]
        if not surface:
            blockers.append("source_map_selected_executor_result_consumer_unsupported")
        expected_schema = str(surface.get("result_schema") or "")
        if expected_schema and result.get("schema_version") != expected_schema:
            blockers.append("source_map_selected_executor_application_result_schema_mismatch")
        if cls._status(result) != "success":
            blockers.append("source_map_selected_executor_application_result_not_success")
        if spec.expected_consumer and consumer and spec.expected_consumer != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_application_result_digest_sha256 and spec.expected_application_result_digest_sha256 != result_digest:
            blockers.append("source_map_selected_executor_application_result_digest_mismatch")
        if result.get("review_approved") is not True:
            blockers.append("source_map_selected_executor_application_result_review_not_approved")
        if result.get("mode") != "apply":
            blockers.append("source_map_selected_executor_application_result_not_apply_mode")
        approval_flag = str(surface.get("approval_flag") or "")
        if approval_flag and result.get(approval_flag) is not True:
            blockers.append("source_map_selected_executor_application_result_approval_flag_missing")
        if gate and surface and gate != str(surface.get("review_gate") or ""):
            blockers.append("source_map_selected_executor_application_result_review_gate_mismatch")
        if consumer and result.get("selected_consumer") and result.get("selected_consumer") != consumer:
            blockers.append("source_map_selected_executor_application_result_consumer_mismatch")
        success_key = str(surface.get("success_key") or "")
        if success_key and result.get(success_key) is not True:
            blockers.append("source_map_selected_executor_application_result_success_flag_missing")
        if result.get("surface_executor_invoked") is not True:
            blockers.append("source_map_selected_executor_application_result_executor_not_invoked")
        blockers.extend(cls._result_side_effect_blockers(result))
        blockers.extend(cls._handoff_blockers(spec, result, handoff, surface, consumer, action_id, gate, handoff_digest))
        if rebuild_generation:
            blockers.extend(cls._rebuild_generation_blockers(rebuild_generation, consumer))
        return blockers

    @classmethod
    def _handoff_blockers(
        cls,
        spec: SourceMapSelectedExecutorResultCheckpointSpec,
        result: dict[str, Any],
        handoff: dict[str, Any],
        surface: dict[str, Any],
        consumer: str,
        action_id: str,
        gate: str,
        handoff_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not handoff:
            return blockers
        if handoff.get("schema_version") != "reverse-deepagent.source-map-selected-executor-application-handoff.v1":
            blockers.append("source_map_selected_executor_application_handoff_schema_mismatch")
        if cls._status(handoff) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_selected_executor_application_handoff_not_ready")
        if handoff.get("ready_for_application_review") is not True:
            blockers.append("source_map_selected_executor_application_handoff_not_ready_for_review")
        if consumer and handoff.get("selected_consumer") and handoff.get("selected_consumer") != consumer:
            blockers.append("source_map_selected_executor_application_handoff_consumer_mismatch")
        if action_id and handoff.get("selected_action_id") and handoff.get("selected_action_id") != action_id:
            blockers.append("source_map_selected_executor_application_handoff_action_mismatch")
        if gate and handoff.get("selected_review_gate") and handoff.get("selected_review_gate") != gate:
            blockers.append("source_map_selected_executor_application_handoff_gate_mismatch")
        result_artifact = str(surface.get("result_artifact") or "")
        if result_artifact and handoff.get("future_result_artifact") and handoff.get("future_result_artifact") != result_artifact:
            blockers.append("source_map_selected_executor_application_handoff_result_artifact_mismatch")
        if spec.expected_application_handoff_digest_sha256 and spec.expected_application_handoff_digest_sha256 != handoff_digest:
            blockers.append("source_map_selected_executor_application_handoff_digest_mismatch")
        if handoff.get("ready_to_execute_now") is True or handoff.get("application_invoked") is True or handoff.get("surface_executor_invoked") is True:
            blockers.append("source_map_selected_executor_application_handoff_execution_claim_detected")
        blockers.extend(SourceMapSelectedExecutorApplyPreflightManager._side_effect_blockers(handoff.get("side_effect_policy") if isinstance(handoff.get("side_effect_policy"), dict) else {}, prefix="source_map_selected_executor_application_handoff"))
        return blockers

    @classmethod
    def _result_side_effect_blockers(cls, result: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        for key in ("calls_mcp", "mobile_runtime_used", "automatic_continuation", "automatic_loop", "automatic_hook_installation", "external_delivery_performed", "delivery_executed"):
            if result.get(key) is True:
                blockers.append(f"source_map_selected_executor_application_result_{key}_forbidden")
        for key in ("raw_source_content_exported", "preview_exported", "raw_source_content_included"):
            if result.get(key) is True:
                blockers.append(f"source_map_selected_executor_application_result_{key}_forbidden")
        return blockers

    @classmethod
    def _rebuild_generation_blockers(cls, rebuild_generation: dict[str, Any], consumer: str) -> list[str]:
        blockers: list[str] = []
        if consumer != "rebuild":
            blockers.append("source_map_rebuild_generation_result_consumer_mismatch")
        if rebuild_generation.get("schema_version") != "reverse-deepagent.source-map-rebuild-generation-result.v1":
            blockers.append("source_map_rebuild_generation_result_schema_mismatch")
        if cls._status(rebuild_generation) not in {"success", "partial"}:
            blockers.append("source_map_rebuild_generation_result_not_reviewable")
        for key in ("calls_mcp", "mobile_runtime_used", "raw_source_content_exported", "preview_exported", "raw_source_content_included", "external_delivery_performed", "delivery_executed"):
            if rebuild_generation.get(key) is True:
                blockers.append(f"source_map_rebuild_generation_result_{key}_forbidden")
        return blockers

    @classmethod
    def _checkpoint_review(cls, surface: dict[str, Any], result: dict[str, Any], rebuild_generation: dict[str, Any], result_digest: str, generation_digest: str) -> dict[str, Any]:
        if not result or not surface:
            return {}
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-result-checkpoint-review.v1",
            "result_kind": surface.get("result_kind", ""),
            "application_surface": surface.get("application_surface", ""),
            "application_result_artifact": surface.get("result_artifact", ""),
            "application_result_digest_sha256": result_digest,
            "selected_action_id": str(result.get("selected_action_id") or ""),
            "selected_consumer": str(result.get("selected_consumer") or ""),
            "selected_review_gate": str(result.get("selected_review_gate") or ""),
            "result_status": cls._status(result),
            "review_approved": bool(result.get("review_approved") is True),
            "surface_executor_invoked": bool(result.get("surface_executor_invoked") is True),
            "success_key": surface.get("success_key", ""),
            "success": bool(result.get(str(surface.get("success_key") or "")) is True),
            "optional_rebuild_generation_result_digest_sha256": generation_digest,
            "optional_rebuild_generation_status": cls._status(rebuild_generation),
            "requires_manual_review": True,
            "execute_next_automatically": False,
            "terminal_checkpoint_candidate": cls._terminal_checkpoint_candidate(result, rebuild_generation),
        }

    @classmethod
    def _warnings(cls, result: dict[str, Any], rebuild_generation: dict[str, Any]) -> list[str]:
        warnings = ["source_map_selected_executor_result_checkpoint_does_not_execute_next_step"]
        if result:
            warnings.append("source_map_selected_executor_application_result_requires_review_before_followthrough_completion")
        if result.get("selected_consumer") == "rebuild" and not rebuild_generation and result.get("rebuild_bundle_generated") is not True:
            warnings.append("source_map_rebuild_metadata_result_may_need_reviewed_generation")
        return warnings

    @classmethod
    def _next_action(cls, blockers: list[str], consumer: str, result: dict[str, Any], rebuild_generation: dict[str, Any]) -> str:
        if any(item.startswith("source_map_selected_executor_application_result_missing") for item in blockers):
            return "provide_source_map_selected_executor_application_result"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_selected_executor_result_checkpoint_inputs"
        if blockers:
            return "inspect_source_map_selected_executor_result_checkpoint_failure"
        if consumer == "rebuild" and result.get("rebuild_bundle_generated") is not True and not rebuild_generation:
            return "review_source_map_rebuild_generation"
        return "review_source_map_selected_executor_result_checkpoint"

    @classmethod
    def _infer_consumer(cls, result: dict[str, Any], handoff: dict[str, Any]) -> str:
        consumer = str(result.get("selected_consumer") or handoff.get("selected_consumer") or "") if result or handoff else ""
        if consumer:
            return consumer
        schema = str(result.get("schema_version") or "")
        if schema == "reverse-deepagent.source-map-debugger-execution-result.v1" or "debugger_location_applied" in result:
            return "debugger"
        if schema == "reverse-deepagent.source-map-hook-install-result.v1" or "hook_installed" in result:
            return "hook"
        if schema == "reverse-deepagent.source-map-rebuild-result.v1" or "rebuild_metadata_applied" in result:
            return "rebuild"
        if "logpoint_installed" in result or "source_logpoint_status" in result:
            return "source-logpoint"
        return ""

    @staticmethod
    def _observed_application_side_effects(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "browser_started": bool(result.get("browser_started") is True),
            "cdp_command_sent": bool(result.get("cdp_command_sent") is True),
            "runtime_evaluated": bool(result.get("runtime_evaluated") is True),
            "debugger_execution_performed": bool(result.get("debugger_execution_performed") is True),
            "logpoint_installed": bool(result.get("logpoint_installed") is True),
            "hook_installed": bool(result.get("hook_installed") is True),
            "rebuild_metadata_applied": bool(result.get("rebuild_metadata_applied") is True),
            "rebuild_executed": bool(result.get("rebuild_executed") is True),
            "calls_mcp": bool(result.get("calls_mcp") is True),
            "mobile_runtime_used": bool(result.get("mobile_runtime_used") is True),
        }

    @staticmethod
    def _terminal_checkpoint_candidate(result: dict[str, Any], rebuild_generation: dict[str, Any]) -> bool:
        if result.get("selected_consumer") == "rebuild" and rebuild_generation:
            return rebuild_generation.get("status") in {"success", "partial"}
        return result.get("status") == "success"

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "checkpoint_only": True,
            "application_result_checkpoint_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughCompletionCheckpointSpec:
    """Read-only completion / next-action checkpoint after a selected-executor result checkpoint."""

    source_map_selected_executor_result_checkpoint: dict[str, Any] = field(default_factory=dict)
    source_map_followthrough_chain_readiness: dict[str, Any] = field(default_factory=dict)
    source_map_rebuild_generation_result: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_result_checkpoint_digest_sha256: str = ""
    expected_chain_readiness_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughCompletionCheckpointSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_completion_checkpoint",
                "sourceMapFollowthroughCompletionCheckpoint",
                "source_map_followthrough_completion_review",
                "sourceMapFollowthroughCompletionReview",
                "source_map_followthrough_next_action_checkpoint",
                "sourceMapFollowthroughNextActionCheckpoint",
            )
        )
        result_checkpoint = cls._object_alias(
            context,
            "source_map_selected_executor_result_checkpoint",
            "source-map-selected-executor-result-checkpoint",
            "sourceMapSelectedExecutorResultCheckpoint",
            "source_map_selected_executor_application_result_checkpoint",
            "source-map-selected-executor-application-result-checkpoint",
            "sourceMapSelectedExecutorApplicationResultCheckpoint",
            "source_map_followthrough_result_checkpoint",
            "source-map-followthrough-result-checkpoint",
            "sourceMapFollowthroughResultCheckpoint",
        )
        chain_readiness = cls._object_alias(
            context,
            "source_map_followthrough_chain_readiness",
            "source-map-followthrough-chain-readiness",
            "sourceMapFollowthroughChainReadiness",
        )
        rebuild_generation = cls._object_alias(
            context,
            "source_map_rebuild_generation_result",
            "source-map-rebuild-generation-result",
            "sourceMapRebuildGenerationResult",
        )
        if not requested and not result_checkpoint:
            return None
        return cls(
            source_map_selected_executor_result_checkpoint=result_checkpoint,
            source_map_followthrough_chain_readiness=chain_readiness,
            source_map_rebuild_generation_result=rebuild_generation,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_result_checkpoint_digest_sha256=str(context.get("expected_result_checkpoint_digest_sha256", context.get("expectedResultCheckpointDigestSha256", "")) or ""),
            expected_chain_readiness_digest_sha256=str(context.get("expected_chain_readiness_digest_sha256", context.get("expectedChainReadinessDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughCompletionCheckpointResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapFollowthroughCompletionCheckpointManager:
    """Normalize a selected-executor result checkpoint into a completion / next-action review checkpoint."""

    def review(self, spec: SourceMapFollowthroughCompletionCheckpointSpec | None) -> SourceMapFollowthroughCompletionCheckpointResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughCompletionCheckpointResult(status="unsupported", reason="missing_source_map_followthrough_completion_checkpoint_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughCompletionCheckpointResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_completion_checkpoint_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughCompletionCheckpointResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_completion_checkpoint_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughCompletionCheckpointSpec) -> dict[str, Any]:
        checkpoint = spec.source_map_selected_executor_result_checkpoint
        chain = spec.source_map_followthrough_chain_readiness
        rebuild_generation = spec.source_map_rebuild_generation_result
        checkpoint_digest = self._stable_json_digest(checkpoint) if checkpoint else ""
        chain_digest = self._stable_json_digest(chain) if chain else ""
        rebuild_generation_digest = self._stable_json_digest(rebuild_generation) if rebuild_generation else ""
        consumer = self._normalize_consumer(str(checkpoint.get("selected_consumer") or chain.get("selected_consumer") or spec.expected_consumer or ""))
        action_id = str(checkpoint.get("selected_action_id") or "")
        blockers = self._blockers(spec, checkpoint, chain, rebuild_generation, consumer, action_id, checkpoint_digest, chain_digest)
        completion = self._completion_review(checkpoint, chain, rebuild_generation, consumer, checkpoint_digest, chain_digest, rebuild_generation_digest, bool(blockers))
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-completion-checkpoint.v1",
            "status": status,
            "review_only": True,
            "checkpoint_only": True,
            "completion_checkpoint_only": True,
            "next_action_checkpoint_only": True,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": str(checkpoint.get("selected_review_gate") or ""),
            "application_surface": str(checkpoint.get("application_surface") or ""),
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer or str(checkpoint.get("reviewer") or ""),
            "source_result_checkpoint_schema_version": str(checkpoint.get("schema_version") or ""),
            "source_result_checkpoint_status": self._status(checkpoint),
            "source_result_checkpoint_digest_sha256": checkpoint_digest,
            "expected_result_checkpoint_digest_sha256": spec.expected_result_checkpoint_digest_sha256,
            "source_chain_readiness_schema_version": str(chain.get("schema_version") or "") if chain else "",
            "source_chain_readiness_status": self._status(chain),
            "source_chain_readiness_digest_sha256": chain_digest,
            "expected_chain_readiness_digest_sha256": spec.expected_chain_readiness_digest_sha256,
            "optional_rebuild_generation_result_schema_version": str(rebuild_generation.get("schema_version") or "") if rebuild_generation else "",
            "optional_rebuild_generation_result_status": self._status(rebuild_generation),
            "optional_rebuild_generation_result_digest_sha256": rebuild_generation_digest,
            "result_checkpoint_verified": bool(checkpoint) and not blockers,
            "chain_readiness_verified": bool(chain) and not self._chain_blockers(spec, checkpoint, chain, consumer, chain_digest),
            "completion_checkpoint_ready": not blockers,
            "terminal_review_candidate": bool(completion.get("terminal_review_candidate")) and not blockers,
            "followup_required": bool(completion.get("followup_required")) and not blockers,
            "completion_status": completion.get("completion_status", "blocked" if blockers else "review_required"),
            "completion_review": completion,
            "ready_for_completion_review": not blockers,
            "ready_for_next_explicit_review": not blockers,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked_by_completion": False,
            "source_logpoint_install_invoked_by_completion": False,
            "rebuild_invoked_by_completion": False,
            "delivery_invoked_by_completion": False,
            "browser_started_by_completion": False,
            "cdp_command_sent_by_completion": False,
            "runtime_evaluated_by_completion": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(checkpoint, rebuild_generation, consumer),
            "next_action": self._next_action(blockers, consumer, completion),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-completion-checkpoint.v1",
            "status": status,
            "review_only": True,
            "checkpoint_only": True,
            "completion_checkpoint_only": True,
            "reason": reason,
            "selected_consumer": "",
            "completion_status": status,
            "completion_checkpoint_ready": False,
            "ready_for_completion_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_selected_executor_result_checkpoint",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapFollowthroughCompletionCheckpointSpec,
        checkpoint: dict[str, Any],
        chain: dict[str, Any],
        rebuild_generation: dict[str, Any],
        consumer: str,
        action_id: str,
        checkpoint_digest: str,
        chain_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not checkpoint:
            return ["source_map_selected_executor_result_checkpoint_missing"]
        if checkpoint.get("schema_version") != "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1":
            blockers.append("source_map_selected_executor_result_checkpoint_schema_mismatch")
        if cls._status(checkpoint) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_selected_executor_result_checkpoint_not_ready")
        if checkpoint.get("application_result_verified") is not True or checkpoint.get("ready_for_next_explicit_review") is not True:
            blockers.append("source_map_selected_executor_result_checkpoint_not_verified")
        if spec.expected_consumer and consumer and cls._normalize_consumer(spec.expected_consumer) != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_result_checkpoint_digest_sha256 and spec.expected_result_checkpoint_digest_sha256 != checkpoint_digest:
            blockers.append("source_map_selected_executor_result_checkpoint_digest_mismatch")
        for key in ("calls_mcp", "mobile_runtime_used", "execute_next_automatically", "ready_to_execute_now"):
            if checkpoint.get(key) is True:
                blockers.append(f"source_map_selected_executor_result_checkpoint_{key}_forbidden")
        blockers.extend(cls._chain_blockers(spec, checkpoint, chain, consumer, chain_digest))
        if rebuild_generation:
            blockers.extend(cls._rebuild_generation_blockers(rebuild_generation, consumer))
        return blockers

    @classmethod
    def _chain_blockers(cls, spec: SourceMapFollowthroughCompletionCheckpointSpec, checkpoint: dict[str, Any], chain: dict[str, Any], consumer: str, chain_digest: str) -> list[str]:
        blockers: list[str] = []
        if not chain:
            return blockers
        if chain.get("schema_version") != "reverse-deepagent.source-map-followthrough-chain-readiness.v1":
            blockers.append("source_map_followthrough_chain_readiness_schema_mismatch")
        if cls._status(chain) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_followthrough_chain_readiness_not_ready")
        if consumer and chain.get("selected_consumer") and cls._normalize_consumer(str(chain.get("selected_consumer"))) != consumer:
            blockers.append("source_map_followthrough_chain_readiness_consumer_mismatch")
        selected_artifact = str(chain.get("selected_result_artifact") or "")
        checkpoint_artifact = str(checkpoint.get("application_result_artifact") or "")
        if selected_artifact and checkpoint_artifact and selected_artifact != checkpoint_artifact:
            blockers.append("source_map_followthrough_chain_readiness_result_artifact_mismatch")
        if spec.expected_chain_readiness_digest_sha256 and spec.expected_chain_readiness_digest_sha256 != chain_digest:
            blockers.append("source_map_followthrough_chain_readiness_digest_mismatch")
        side_effect_policy = chain.get("side_effect_policy") if isinstance(chain.get("side_effect_policy"), dict) else {}
        blockers.extend(SourceMapSelectedExecutorApplyPreflightManager._side_effect_blockers(side_effect_policy, prefix="source_map_followthrough_chain_readiness"))
        return blockers

    @classmethod
    def _rebuild_generation_blockers(cls, rebuild_generation: dict[str, Any], consumer: str) -> list[str]:
        blockers: list[str] = []
        if consumer != "rebuild":
            blockers.append("source_map_rebuild_generation_completion_consumer_mismatch")
        if rebuild_generation.get("schema_version") != "reverse-deepagent.source-map-rebuild-generation-result.v1":
            blockers.append("source_map_rebuild_generation_result_schema_mismatch")
        if cls._status(rebuild_generation) not in {"success", "partial"}:
            blockers.append("source_map_rebuild_generation_result_not_reviewable")
        for key in ("calls_mcp", "mobile_runtime_used", "raw_source_content_exported", "preview_exported", "raw_source_content_included", "delivery_executed", "external_delivery_performed"):
            if rebuild_generation.get(key) is True:
                blockers.append(f"source_map_rebuild_generation_result_{key}_forbidden")
        return blockers

    @classmethod
    def _completion_review(
        cls,
        checkpoint: dict[str, Any],
        chain: dict[str, Any],
        rebuild_generation: dict[str, Any],
        consumer: str,
        checkpoint_digest: str,
        chain_digest: str,
        rebuild_generation_digest: str,
        blocked: bool,
    ) -> dict[str, Any]:
        if not checkpoint:
            return {}
        followup = cls._consumer_followup(consumer, checkpoint, rebuild_generation)
        completion_status = "blocked" if blocked else followup["completion_status"]
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-completion-review.v1",
            "selected_consumer": consumer,
            "selected_action_id": str(checkpoint.get("selected_action_id") or ""),
            "application_surface": str(checkpoint.get("application_surface") or ""),
            "result_checkpoint_digest_sha256": checkpoint_digest,
            "chain_readiness_digest_sha256": chain_digest,
            "rebuild_generation_result_digest_sha256": rebuild_generation_digest,
            "application_result_status": str(checkpoint.get("application_result_status") or ""),
            "application_result_verified": bool(checkpoint.get("application_result_verified") is True),
            "chain_readiness_present": bool(chain),
            "rebuild_generation_present": bool(rebuild_generation),
            "completion_status": completion_status,
            "terminal_review_candidate": bool(followup["terminal_review_candidate"]) and not blocked,
            "followup_required": bool(followup["followup_required"]) and not blocked,
            "followup_type": followup["followup_type"],
            "recommended_review_action": followup["recommended_review_action"],
            "required_artifacts": followup["required_artifacts"],
            "execute_automatically": False,
            "requires_manual_review": True,
        }

    @staticmethod
    def _consumer_followup(consumer: str, checkpoint: dict[str, Any], rebuild_generation: dict[str, Any]) -> dict[str, Any]:
        if consumer == "rebuild":
            generation_ready = bool(rebuild_generation) and rebuild_generation.get("status") in {"success", "partial"}
            if generation_ready and rebuild_generation.get("rebuild_bundle_generated") is True:
                return {
                    "completion_status": "terminal_review_candidate",
                    "terminal_review_candidate": True,
                    "followup_required": False,
                    "followup_type": "review_generated_rebuild_bundle",
                    "recommended_review_action": "review_generated_rebuild_bundle_before_delivery",
                    "required_artifacts": ["workspace/source-map-rebuild-generation-result.json"],
                }
            return {
                "completion_status": "followup_required",
                "terminal_review_candidate": False,
                "followup_required": True,
                "followup_type": "reviewed_rebuild_generation_required",
                "recommended_review_action": "review_source_map_rebuild_generation",
                "required_artifacts": ["workspace/source-map-rebuild-result.json"],
            }
        if consumer == "debugger":
            return {
                "completion_status": "terminal_review_candidate",
                "terminal_review_candidate": True,
                "followup_required": False,
                "followup_type": "debugger_artifact_review",
                "recommended_review_action": "inspect_source_map_debugger_execution_artifacts",
                "required_artifacts": ["workspace/source-map-debugger-execution-result.json", "workspace/breakpoints.json"],
            }
        if consumer == "source-logpoint":
            return {
                "completion_status": "terminal_review_candidate",
                "terminal_review_candidate": True,
                "followup_required": False,
                "followup_type": "source_logpoint_timeline_review",
                "recommended_review_action": "inspect_source_map_source_logpoint_events",
                "required_artifacts": ["workspace/source-map-source-logpoint-install-result.json", "workspace/source-logpoint-timeline.json"],
            }
        if consumer == "hook":
            return {
                "completion_status": "terminal_review_candidate",
                "terminal_review_candidate": True,
                "followup_required": False,
                "followup_type": "hook_timeline_review",
                "recommended_review_action": "inspect_source_map_hook_install_timeline",
                "required_artifacts": ["workspace/source-map-hook-install-result.json"],
            }
        return {
            "completion_status": "followup_required",
            "terminal_review_candidate": False,
            "followup_required": True,
            "followup_type": "unknown_consumer_review",
            "recommended_review_action": "review_source_map_selected_executor_result_checkpoint",
            "required_artifacts": ["workspace/source-map-selected-executor-result-checkpoint.json"],
        }

    @classmethod
    def _warnings(cls, checkpoint: dict[str, Any], rebuild_generation: dict[str, Any], consumer: str) -> list[str]:
        warnings = ["source_map_followthrough_completion_checkpoint_does_not_execute_next_step"]
        if checkpoint:
            warnings.append("source_map_followthrough_completion_requires_manual_review")
        if consumer == "rebuild" and not rebuild_generation:
            warnings.append("source_map_rebuild_generation_not_attached_to_completion_checkpoint")
        return warnings

    @classmethod
    def _next_action(cls, blockers: list[str], consumer: str, completion: dict[str, Any]) -> str:
        if any(item == "source_map_selected_executor_result_checkpoint_missing" for item in blockers):
            return "provide_source_map_selected_executor_result_checkpoint"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_followthrough_completion_checkpoint_inputs"
        if blockers:
            return "inspect_source_map_followthrough_completion_checkpoint_failure"
        return str(completion.get("recommended_review_action") or "review_source_map_followthrough_completion_checkpoint")

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        normalized = value.strip().replace("_", "-").lower()
        aliases = {"source-logpoints": "source-logpoint", "logpoint": "source-logpoint", "logpoints": "source-logpoint", "rebuild-metadata": "rebuild"}
        return aliases.get(normalized, normalized)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "checkpoint_only": True,
            "completion_checkpoint_only": True,
            "next_action_checkpoint_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "delivery_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapTerminalReviewPackageSpec:
    """Read-only terminal review package / audit handoff after a Source Map completion checkpoint."""

    source_map_followthrough_completion_checkpoint: dict[str, Any] = field(default_factory=dict)
    source_map_selected_executor_result_checkpoint: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_completion_checkpoint_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapTerminalReviewPackageSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_terminal_review_package",
                "sourceMapTerminalReviewPackage",
                "source_map_followthrough_terminal_review_package",
                "sourceMapFollowthroughTerminalReviewPackage",
                "source_map_terminal_review_handoff",
                "sourceMapTerminalReviewHandoff",
                "source_map_followthrough_audit_handoff",
                "sourceMapFollowthroughAuditHandoff",
            )
        )
        completion = cls._object_alias(
            context,
            "source_map_followthrough_completion_checkpoint",
            "source-map-followthrough-completion-checkpoint",
            "sourceMapFollowthroughCompletionCheckpoint",
            "source_map_followthrough_completion_review",
            "source-map-followthrough-completion-review",
            "sourceMapFollowthroughCompletionReview",
            "source_map_followthrough_next_action_checkpoint",
            "source-map-followthrough-next-action-checkpoint",
            "sourceMapFollowthroughNextActionCheckpoint",
        )
        result_checkpoint = cls._object_alias(
            context,
            "source_map_selected_executor_result_checkpoint",
            "source-map-selected-executor-result-checkpoint",
            "sourceMapSelectedExecutorResultCheckpoint",
            "source_map_followthrough_result_checkpoint",
            "source-map-followthrough-result-checkpoint",
            "sourceMapFollowthroughResultCheckpoint",
        )
        if not requested and not completion:
            return None
        return cls(
            source_map_followthrough_completion_checkpoint=completion,
            source_map_selected_executor_result_checkpoint=result_checkpoint,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_completion_checkpoint_digest_sha256=str(context.get("expected_completion_checkpoint_digest_sha256", context.get("expectedCompletionCheckpointDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapTerminalReviewPackageResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapTerminalReviewPackageManager:
    """Package a completion checkpoint into a terminal review / audit handoff descriptor without executing next actions."""

    def review(self, spec: SourceMapTerminalReviewPackageSpec | None) -> SourceMapTerminalReviewPackageResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapTerminalReviewPackageResult(status="unsupported", reason="missing_source_map_terminal_review_package_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapTerminalReviewPackageResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_terminal_review_package_failed")
            descriptor["error"] = str(exc)
            return SourceMapTerminalReviewPackageResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_terminal_review_package_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapTerminalReviewPackageSpec) -> dict[str, Any]:
        completion = spec.source_map_followthrough_completion_checkpoint
        result_checkpoint = spec.source_map_selected_executor_result_checkpoint
        completion_digest = self._stable_json_digest(completion) if completion else ""
        result_checkpoint_digest = self._stable_json_digest(result_checkpoint) if result_checkpoint else ""
        consumer = self._normalize_consumer(str(completion.get("selected_consumer") or spec.expected_consumer or ""))
        action_id = str(completion.get("selected_action_id") or "")
        blockers = self._blockers(spec, completion, result_checkpoint, consumer, action_id, completion_digest)
        review_package = self._review_package(completion, result_checkpoint, consumer, completion_digest, result_checkpoint_digest, bool(blockers))
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-package.v1",
            "status": status,
            "review_only": True,
            "audit_handoff_only": True,
            "terminal_review_package_only": True,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": str(completion.get("selected_review_gate") or ""),
            "application_surface": str(completion.get("application_surface") or ""),
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer or str(completion.get("reviewer") or ""),
            "source_completion_checkpoint_schema_version": str(completion.get("schema_version") or "") if completion else "",
            "source_completion_checkpoint_status": self._status(completion),
            "source_completion_checkpoint_digest_sha256": completion_digest,
            "expected_completion_checkpoint_digest_sha256": spec.expected_completion_checkpoint_digest_sha256,
            "source_result_checkpoint_schema_version": str(result_checkpoint.get("schema_version") or "") if result_checkpoint else "",
            "source_result_checkpoint_digest_sha256": result_checkpoint_digest,
            "completion_checkpoint_verified": bool(completion) and not blockers,
            "result_checkpoint_attached": bool(result_checkpoint),
            "terminal_review_candidate": bool(completion.get("terminal_review_candidate")) and not blockers,
            "followup_required": bool(completion.get("followup_required")) and not blockers,
            "completion_status": str(completion.get("completion_status") or ("blocked" if blockers else "review_required")),
            "terminal_review_package": review_package,
            "ready_for_terminal_review": not blockers,
            "ready_for_audit_handoff_review": not blockers,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "recommended_action_executed": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked_by_package": False,
            "source_logpoint_install_invoked_by_package": False,
            "rebuild_invoked_by_package": False,
            "delivery_invoked_by_package": False,
            "browser_started_by_package": False,
            "cdp_command_sent_by_package": False,
            "runtime_evaluated_by_package": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(completion),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-package.v1",
            "status": status,
            "review_only": True,
            "audit_handoff_only": True,
            "terminal_review_package_only": True,
            "reason": reason,
            "selected_consumer": "",
            "completion_status": status,
            "ready_for_terminal_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_followthrough_completion_checkpoint",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapTerminalReviewPackageSpec,
        completion: dict[str, Any],
        result_checkpoint: dict[str, Any],
        consumer: str,
        action_id: str,
        completion_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not completion:
            return ["source_map_followthrough_completion_checkpoint_missing"]
        if completion.get("schema_version") != "reverse-deepagent.source-map-followthrough-completion-checkpoint.v1":
            blockers.append("source_map_followthrough_completion_checkpoint_schema_mismatch")
        if cls._status(completion) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_followthrough_completion_checkpoint_not_ready")
        if completion.get("ready_for_completion_review") is not True or completion.get("completion_checkpoint_ready") is not True:
            blockers.append("source_map_followthrough_completion_checkpoint_not_verified")
        if not completion.get("terminal_review_candidate") and not completion.get("followup_required"):
            blockers.append("source_map_followthrough_completion_checkpoint_no_terminal_or_followup_state")
        if spec.expected_consumer and consumer and cls._normalize_consumer(spec.expected_consumer) != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_completion_checkpoint_digest_sha256 and spec.expected_completion_checkpoint_digest_sha256 != completion_digest:
            blockers.append("source_map_followthrough_completion_checkpoint_digest_mismatch")
        for key in ("calls_mcp", "mobile_runtime_used", "execute_next_automatically", "ready_to_execute_now", "debugger_continuation_invoked", "rebuild_invoked_by_completion", "delivery_invoked_by_completion"):
            if completion.get(key) is True:
                blockers.append(f"source_map_followthrough_completion_checkpoint_{key}_forbidden")
        if result_checkpoint:
            if result_checkpoint.get("schema_version") != "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1":
                blockers.append("source_map_selected_executor_result_checkpoint_schema_mismatch")
            if consumer and result_checkpoint.get("selected_consumer") and cls._normalize_consumer(str(result_checkpoint.get("selected_consumer"))) != consumer:
                blockers.append("source_map_selected_executor_result_checkpoint_consumer_mismatch")
        return blockers

    @classmethod
    def _review_package(cls, completion: dict[str, Any], result_checkpoint: dict[str, Any], consumer: str, completion_digest: str, result_checkpoint_digest: str, blocked: bool) -> dict[str, Any]:
        if not completion:
            return {}
        completion_review = completion.get("completion_review") if isinstance(completion.get("completion_review"), dict) else {}
        recommended = str(completion_review.get("recommended_review_action") or completion.get("next_action") or "review_source_map_followthrough_completion_checkpoint")
        required_artifacts = completion_review.get("required_artifacts") if isinstance(completion_review.get("required_artifacts"), list) else []
        package_kind = "blocked" if blocked else "followup-review-package" if completion.get("followup_required") else "terminal-review-package"
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-package.payload.v1",
            "package_kind": package_kind,
            "selected_consumer": consumer,
            "selected_action_id": str(completion.get("selected_action_id") or ""),
            "application_surface": str(completion.get("application_surface") or ""),
            "completion_status": str(completion.get("completion_status") or ""),
            "terminal_review_candidate": bool(completion.get("terminal_review_candidate")) and not blocked,
            "followup_required": bool(completion.get("followup_required")) and not blocked,
            "recommended_review_action": recommended,
            "required_artifacts": required_artifacts,
            "completion_checkpoint_digest_sha256": completion_digest,
            "result_checkpoint_digest_sha256": result_checkpoint_digest,
            "result_checkpoint_attached": bool(result_checkpoint),
            "manual_review_required": True,
            "execute_recommended_action": False,
            "review_steps": cls._review_steps(completion, recommended, required_artifacts, bool(result_checkpoint)),
        }

    @staticmethod
    def _review_steps(completion: dict[str, Any], recommended: str, required_artifacts: list[Any], has_result_checkpoint: bool) -> list[dict[str, Any]]:
        steps = [
            {"order": 1, "action": "inspect_source_map_followthrough_completion_checkpoint", "artifact": "workspace/source-map-followthrough-completion-checkpoint.json", "required": True},
        ]
        if has_result_checkpoint:
            steps.append({"order": len(steps) + 1, "action": "inspect_source_map_selected_executor_result_checkpoint", "artifact": "workspace/source-map-selected-executor-result-checkpoint.json", "required": False})
        for artifact in required_artifacts:
            steps.append({"order": len(steps) + 1, "action": "inspect_required_source_map_review_artifact", "artifact": str(artifact), "required": True})
        steps.append({"order": len(steps) + 1, "action": recommended, "artifact": "", "required": bool(recommended), "execute_automatically": False})
        return steps

    @staticmethod
    def _warnings(completion: dict[str, Any]) -> list[str]:
        warnings = ["source_map_terminal_review_package_does_not_execute_recommended_action"]
        if completion:
            warnings.append("source_map_terminal_review_package_requires_manual_review")
        if completion.get("followup_required") is True:
            warnings.append("source_map_terminal_review_package_followup_required")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if any(item == "source_map_followthrough_completion_checkpoint_missing" for item in blockers):
            return "provide_source_map_followthrough_completion_checkpoint"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_terminal_review_package_inputs"
        if blockers:
            return "inspect_source_map_terminal_review_package_failure"
        return "review_source_map_terminal_review_package"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughCompletionCheckpointManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "audit_handoff_only": True,
            "terminal_review_package_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "recommended_action_executed": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "delivery_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapTerminalReviewClosureCheckpointSpec:
    """Read-only observed-result / closure audit checkpoint after a Source Map terminal review package."""

    source_map_terminal_review_package: dict[str, Any] = field(default_factory=dict)
    source_map_terminal_review_observed_result: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_terminal_review_package_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapTerminalReviewClosureCheckpointSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_terminal_review_closure_checkpoint",
                "sourceMapTerminalReviewClosureCheckpoint",
                "source_map_terminal_review_observed_result_checkpoint",
                "sourceMapTerminalReviewObservedResultCheckpoint",
                "source_map_followthrough_closure_audit",
                "sourceMapFollowthroughClosureAudit",
                "source_map_terminal_review_closure_audit",
                "sourceMapTerminalReviewClosureAudit",
            )
        )
        package = cls._object_alias(
            context,
            "source_map_terminal_review_package",
            "source-map-terminal-review-package",
            "sourceMapTerminalReviewPackage",
            "source_map_followthrough_terminal_review_package",
            "source-map-followthrough-terminal-review-package",
            "sourceMapFollowthroughTerminalReviewPackage",
            "source_map_terminal_review_handoff",
            "source-map-terminal-review-handoff",
            "sourceMapTerminalReviewHandoff",
            "source_map_followthrough_audit_handoff",
            "source-map-followthrough-audit-handoff",
            "sourceMapFollowthroughAuditHandoff",
        )
        observed = cls._object_alias(
            context,
            "source_map_terminal_review_observed_result",
            "source-map-terminal-review-observed-result",
            "sourceMapTerminalReviewObservedResult",
            "source_map_terminal_review_result",
            "source-map-terminal-review-result",
            "sourceMapTerminalReviewResult",
            "source_map_followthrough_terminal_review_observed_result",
            "source-map-followthrough-terminal-review-observed-result",
            "sourceMapFollowthroughTerminalReviewObservedResult",
        )
        if not requested and not package:
            return None
        return cls(
            source_map_terminal_review_package=package,
            source_map_terminal_review_observed_result=observed,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_terminal_review_package_digest_sha256=str(context.get("expected_terminal_review_package_digest_sha256", context.get("expectedTerminalReviewPackageDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapTerminalReviewClosureCheckpointResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapTerminalReviewClosureCheckpointManager:
    """Checkpoint an observed terminal-review result into closure audit evidence without executing follow-ups."""

    def review(self, spec: SourceMapTerminalReviewClosureCheckpointSpec | None) -> SourceMapTerminalReviewClosureCheckpointResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapTerminalReviewClosureCheckpointResult(status="unsupported", reason="missing_source_map_terminal_review_closure_checkpoint_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapTerminalReviewClosureCheckpointResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_terminal_review_closure_checkpoint_failed")
            descriptor["error"] = str(exc)
            return SourceMapTerminalReviewClosureCheckpointResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_terminal_review_closure_checkpoint_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapTerminalReviewClosureCheckpointSpec) -> dict[str, Any]:
        package = spec.source_map_terminal_review_package
        observed = spec.source_map_terminal_review_observed_result
        review_payload = package.get("terminal_review_package") if isinstance(package.get("terminal_review_package"), dict) else {}
        package_digest = self._stable_json_digest(package) if package else ""
        observed_digest = self._stable_json_digest(observed) if observed else ""
        consumer = self._normalize_consumer(str(package.get("selected_consumer") or spec.expected_consumer or ""))
        action_id = str(package.get("selected_action_id") or "")
        blockers = self._blockers(spec, package, observed, consumer, action_id, package_digest)
        status = "blocked" if blockers else "ready_for_review"
        closure_status = self._closure_status(package, observed, bool(blockers))
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1",
            "status": status,
            "review_only": True,
            "audit_checkpoint_only": True,
            "closure_checkpoint_only": True,
            "observed_result_checkpoint_only": True,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": str(package.get("selected_review_gate") or ""),
            "application_surface": str(package.get("application_surface") or ""),
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer or str(observed.get("reviewer") or package.get("reviewer") or ""),
            "source_terminal_review_package_schema_version": str(package.get("schema_version") or "") if package else "",
            "source_terminal_review_package_status": self._status(package),
            "source_terminal_review_package_digest_sha256": package_digest,
            "expected_terminal_review_package_digest_sha256": spec.expected_terminal_review_package_digest_sha256,
            "source_observed_result_schema_version": str(observed.get("schema_version") or "") if observed else "",
            "source_observed_result_status": self._observed_status(observed),
            "source_observed_result_digest_sha256": observed_digest,
            "terminal_review_package_verified": bool(package) and not blockers,
            "observed_result_attached": bool(observed),
            "observed_review_completed": not blockers,
            "terminal_review_candidate": bool(package.get("terminal_review_candidate")) and not blockers,
            "followup_required": bool(package.get("followup_required")) and not blockers,
            "completion_status": str(package.get("completion_status") or ("blocked" if blockers else "review_required")),
            "closure_status": closure_status,
            "recommended_review_action": str(review_payload.get("recommended_review_action") or package.get("next_action") or ""),
            "observed_review_action": self._observed_action(observed, review_payload),
            "required_artifacts": review_payload.get("required_artifacts") if isinstance(review_payload.get("required_artifacts"), list) else [],
            "closure_audit": self._closure_audit(package, observed, review_payload, package_digest, observed_digest, closure_status, bool(blockers)),
            "ready_for_closure_audit_review": not blockers,
            "ready_for_terminal_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "recommended_action_executed_by_checkpoint": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked_by_checkpoint": False,
            "source_logpoint_install_invoked_by_checkpoint": False,
            "rebuild_invoked_by_checkpoint": False,
            "delivery_invoked_by_checkpoint": False,
            "browser_started_by_checkpoint": False,
            "cdp_command_sent_by_checkpoint": False,
            "runtime_evaluated_by_checkpoint": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(package),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1",
            "status": status,
            "review_only": True,
            "audit_checkpoint_only": True,
            "closure_checkpoint_only": True,
            "observed_result_checkpoint_only": True,
            "reason": reason,
            "selected_consumer": "",
            "closure_status": status,
            "ready_for_closure_audit_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_terminal_review_package",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapTerminalReviewClosureCheckpointSpec,
        package: dict[str, Any],
        observed: dict[str, Any],
        consumer: str,
        action_id: str,
        package_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not package:
            return ["source_map_terminal_review_package_missing"]
        if package.get("schema_version") != "reverse-deepagent.source-map-terminal-review-package.v1":
            blockers.append("source_map_terminal_review_package_schema_mismatch")
        if cls._status(package) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_terminal_review_package_not_ready")
        if package.get("ready_for_terminal_review") is not True or package.get("ready_for_audit_handoff_review") is not True:
            blockers.append("source_map_terminal_review_package_not_verified")
        if spec.expected_consumer and consumer and cls._normalize_consumer(spec.expected_consumer) != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_terminal_review_package_digest_sha256 and spec.expected_terminal_review_package_digest_sha256 != package_digest:
            blockers.append("source_map_terminal_review_package_digest_mismatch")
        for key in ("calls_mcp", "mobile_runtime_used", "execute_next_automatically", "ready_to_execute_now", "recommended_action_executed", "debugger_continuation_invoked", "hook_install_invoked_by_package", "source_logpoint_install_invoked_by_package", "rebuild_invoked_by_package", "delivery_invoked_by_package", "browser_started_by_package", "cdp_command_sent_by_package", "runtime_evaluated_by_package"):
            if package.get(key) is True:
                blockers.append(f"source_map_terminal_review_package_{key}_forbidden")
        if not observed:
            blockers.append("source_map_terminal_review_observed_result_missing")
        else:
            if cls._observed_status(observed) in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_terminal_review_observed_result_failed")
            if not cls._observed_completed(observed):
                blockers.append("source_map_terminal_review_observed_result_not_completed")
            for key in ("calls_mcp", "mobile_runtime_used", "checkpoint_executed", "browser_started_by_checkpoint", "cdp_command_sent_by_checkpoint", "runtime_evaluated_by_checkpoint", "recommended_action_executed_by_checkpoint"):
                if observed.get(key) is True:
                    blockers.append(f"source_map_terminal_review_observed_result_{key}_forbidden")
        return blockers

    @classmethod
    def _closure_audit(
        cls,
        package: dict[str, Any],
        observed: dict[str, Any],
        review_payload: dict[str, Any],
        package_digest: str,
        observed_digest: str,
        closure_status: str,
        blocked: bool,
    ) -> dict[str, Any]:
        if not package:
            return {}
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-closure-audit.v1",
            "audit_kind": "source-map-terminal-review-closure",
            "selected_consumer": str(package.get("selected_consumer") or ""),
            "selected_action_id": str(package.get("selected_action_id") or ""),
            "application_surface": str(package.get("application_surface") or ""),
            "package_kind": str(review_payload.get("package_kind") or ""),
            "closure_status": closure_status,
            "terminal_review_candidate": bool(package.get("terminal_review_candidate")) and not blocked,
            "followup_required": bool(package.get("followup_required")) and not blocked,
            "recommended_review_action": str(review_payload.get("recommended_review_action") or package.get("next_action") or ""),
            "observed_review_action": cls._observed_action(observed, review_payload),
            "observed_result_status": cls._observed_status(observed),
            "terminal_review_package_digest_sha256": package_digest,
            "observed_result_digest_sha256": observed_digest,
            "manual_review_observed": bool(observed) and not blocked,
            "closure_review_required": True,
            "execute_recommended_action": False,
            "required_artifacts": review_payload.get("required_artifacts") if isinstance(review_payload.get("required_artifacts"), list) else [],
            "review_notes_digest_sha256": cls._review_notes_digest(observed),
        }

    @staticmethod
    def _closure_status(package: dict[str, Any], observed: dict[str, Any], blocked: bool) -> str:
        if blocked:
            if not observed:
                return "observed_result_required"
            return "blocked"
        if package.get("followup_required") is True:
            return "followup_review_observed"
        return "terminal_review_observed"

    @staticmethod
    def _observed_status(observed: dict[str, Any]) -> str:
        return str(observed.get("status") or observed.get("review_status") or observed.get("result_status") or "").strip().lower()

    @classmethod
    def _observed_completed(cls, observed: dict[str, Any]) -> bool:
        if observed.get("review_completed") is True or observed.get("manual_review_completed") is True or observed.get("closure_ready") is True:
            return True
        return cls._observed_status(observed) in {"reviewed", "accepted", "approved", "completed", "success", "closed", "ready_for_review", "followup_recorded", "terminal_review_observed"}

    @staticmethod
    def _observed_action(observed: dict[str, Any], review_payload: dict[str, Any]) -> str:
        return str(observed.get("observed_review_action") or observed.get("review_action") or observed.get("action") or review_payload.get("recommended_review_action") or "")

    @staticmethod
    def _review_notes_digest(observed: dict[str, Any]) -> str:
        notes = observed.get("review_notes", observed.get("notes", ""))
        if not notes:
            return ""
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest({"review_notes": str(notes)})

    @staticmethod
    def _warnings(package: dict[str, Any]) -> list[str]:
        warnings = ["source_map_terminal_review_closure_checkpoint_does_not_execute_recommended_action"]
        if package:
            warnings.append("source_map_terminal_review_closure_checkpoint_requires_manual_review")
        if package.get("followup_required") is True:
            warnings.append("source_map_terminal_review_closure_checkpoint_followup_observed")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if any(item == "source_map_terminal_review_package_missing" for item in blockers):
            return "provide_source_map_terminal_review_package"
        if any(item == "source_map_terminal_review_observed_result_missing" for item in blockers):
            return "record_source_map_terminal_review_observed_result"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_terminal_review_closure_checkpoint_inputs"
        if blockers:
            return "inspect_source_map_terminal_review_closure_checkpoint_failure"
        return "review_source_map_terminal_review_closure_checkpoint"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughCompletionCheckpointManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "audit_checkpoint_only": True,
            "closure_checkpoint_only": True,
            "observed_result_checkpoint_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "recommended_action_executed_by_checkpoint": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "delivery_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapTerminalReviewFinalAuditSpec:
    """Read-only final audit rollup after a Source Map terminal review closure checkpoint."""

    source_map_terminal_review_closure_checkpoint: dict[str, Any] = field(default_factory=dict)
    source_map_terminal_review_package: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_closure_checkpoint_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapTerminalReviewFinalAuditSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_terminal_review_final_audit",
                "sourceMapTerminalReviewFinalAudit",
                "source_map_terminal_review_final_audit_rollup",
                "sourceMapTerminalReviewFinalAuditRollup",
                "source_map_followthrough_final_audit",
                "sourceMapFollowthroughFinalAudit",
                "source_map_terminal_review_closure_summary",
                "sourceMapTerminalReviewClosureSummary",
            )
        )
        closure = cls._object_alias(
            context,
            "source_map_terminal_review_closure_checkpoint",
            "source-map-terminal-review-closure-checkpoint",
            "sourceMapTerminalReviewClosureCheckpoint",
            "source_map_terminal_review_observed_result_checkpoint",
            "source-map-terminal-review-observed-result-checkpoint",
            "sourceMapTerminalReviewObservedResultCheckpoint",
            "source_map_followthrough_closure_audit",
            "source-map-followthrough-closure-audit",
            "sourceMapFollowthroughClosureAudit",
            "source_map_terminal_review_closure_audit",
            "source-map-terminal-review-closure-audit",
            "sourceMapTerminalReviewClosureAudit",
        )
        package = cls._object_alias(
            context,
            "source_map_terminal_review_package",
            "source-map-terminal-review-package",
            "sourceMapTerminalReviewPackage",
            "source_map_followthrough_terminal_review_package",
            "source-map-followthrough-terminal-review-package",
            "sourceMapFollowthroughTerminalReviewPackage",
        )
        if not requested and not closure:
            return None
        return cls(
            source_map_terminal_review_closure_checkpoint=closure,
            source_map_terminal_review_package=package,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_closure_checkpoint_digest_sha256=str(context.get("expected_closure_checkpoint_digest_sha256", context.get("expectedClosureCheckpointDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapTerminalReviewFinalAuditResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapTerminalReviewFinalAuditManager:
    """Summarize a closure checkpoint into final Source Map follow-through audit evidence without execution."""

    def review(self, spec: SourceMapTerminalReviewFinalAuditSpec | None) -> SourceMapTerminalReviewFinalAuditResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapTerminalReviewFinalAuditResult(status="unsupported", reason="missing_source_map_terminal_review_final_audit_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapTerminalReviewFinalAuditResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_terminal_review_final_audit_failed")
            descriptor["error"] = str(exc)
            return SourceMapTerminalReviewFinalAuditResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_terminal_review_final_audit_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapTerminalReviewFinalAuditSpec) -> dict[str, Any]:
        closure = spec.source_map_terminal_review_closure_checkpoint
        package = spec.source_map_terminal_review_package
        closure_audit = closure.get("closure_audit") if isinstance(closure.get("closure_audit"), dict) else {}
        closure_digest = self._stable_json_digest(closure) if closure else ""
        package_digest = self._stable_json_digest(package) if package else ""
        consumer = self._normalize_consumer(str(closure.get("selected_consumer") or spec.expected_consumer or ""))
        action_id = str(closure.get("selected_action_id") or "")
        blockers = self._blockers(spec, closure, package, consumer, action_id, closure_digest)
        status = "blocked" if blockers else "ready_for_review"
        final_status = "blocked" if blockers else "source_map_followthrough_review_closed"
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-final-audit.v1",
            "status": status,
            "review_only": True,
            "audit_rollup_only": True,
            "final_audit_only": True,
            "closure_summary_only": True,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": str(closure.get("selected_review_gate") or ""),
            "application_surface": str(closure.get("application_surface") or ""),
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer or str(closure.get("reviewer") or ""),
            "source_closure_checkpoint_schema_version": str(closure.get("schema_version") or "") if closure else "",
            "source_closure_checkpoint_status": self._status(closure),
            "source_closure_checkpoint_digest_sha256": closure_digest,
            "expected_closure_checkpoint_digest_sha256": spec.expected_closure_checkpoint_digest_sha256,
            "source_terminal_review_package_digest_sha256": str(closure.get("source_terminal_review_package_digest_sha256") or package_digest),
            "terminal_review_package_attached": bool(package),
            "closure_checkpoint_verified": bool(closure) and not blockers,
            "closure_status": str(closure.get("closure_status") or ""),
            "final_audit_status": final_status,
            "terminal_review_candidate": bool(closure.get("terminal_review_candidate")) and not blockers,
            "followup_required": bool(closure.get("followup_required")) and not blockers,
            "observed_review_action": str(closure.get("observed_review_action") or closure_audit.get("observed_review_action") or ""),
            "recommended_review_action": str(closure.get("recommended_review_action") or closure_audit.get("recommended_review_action") or ""),
            "required_artifacts": closure.get("required_artifacts") if isinstance(closure.get("required_artifacts"), list) else closure_audit.get("required_artifacts", []),
            "final_audit_rollup": self._rollup(closure, closure_audit, closure_digest, package_digest, final_status, bool(blockers)),
            "ready_for_final_audit_review": not blockers,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "recommended_action_executed_by_rollup": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked_by_rollup": False,
            "source_logpoint_install_invoked_by_rollup": False,
            "rebuild_invoked_by_rollup": False,
            "delivery_invoked_by_rollup": False,
            "browser_started_by_rollup": False,
            "cdp_command_sent_by_rollup": False,
            "runtime_evaluated_by_rollup": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(closure),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-final-audit.v1",
            "status": status,
            "review_only": True,
            "audit_rollup_only": True,
            "final_audit_only": True,
            "closure_summary_only": True,
            "reason": reason,
            "selected_consumer": "",
            "final_audit_status": status,
            "ready_for_final_audit_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_terminal_review_closure_checkpoint",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapTerminalReviewFinalAuditSpec,
        closure: dict[str, Any],
        package: dict[str, Any],
        consumer: str,
        action_id: str,
        closure_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not closure:
            return ["source_map_terminal_review_closure_checkpoint_missing"]
        if closure.get("schema_version") != "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1":
            blockers.append("source_map_terminal_review_closure_checkpoint_schema_mismatch")
        if cls._status(closure) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_terminal_review_closure_checkpoint_not_ready")
        if closure.get("ready_for_closure_audit_review") is not True or closure.get("observed_review_completed") is not True:
            blockers.append("source_map_terminal_review_closure_checkpoint_not_verified")
        if spec.expected_consumer and consumer and cls._normalize_consumer(spec.expected_consumer) != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_closure_checkpoint_digest_sha256 and spec.expected_closure_checkpoint_digest_sha256 != closure_digest:
            blockers.append("source_map_terminal_review_closure_checkpoint_digest_mismatch")
        for key in ("calls_mcp", "mobile_runtime_used", "execute_next_automatically", "ready_to_execute_now", "recommended_action_executed_by_checkpoint", "debugger_continuation_invoked", "hook_install_invoked_by_checkpoint", "source_logpoint_install_invoked_by_checkpoint", "rebuild_invoked_by_checkpoint", "delivery_invoked_by_checkpoint", "browser_started_by_checkpoint", "cdp_command_sent_by_checkpoint", "runtime_evaluated_by_checkpoint"):
            if closure.get(key) is True:
                blockers.append(f"source_map_terminal_review_closure_checkpoint_{key}_forbidden")
        if package and package.get("schema_version") != "reverse-deepagent.source-map-terminal-review-package.v1":
            blockers.append("source_map_terminal_review_package_schema_mismatch")
        return blockers

    @classmethod
    def _rollup(cls, closure: dict[str, Any], closure_audit: dict[str, Any], closure_digest: str, package_digest: str, final_status: str, blocked: bool) -> dict[str, Any]:
        if not closure:
            return {}
        required_artifacts = closure.get("required_artifacts") if isinstance(closure.get("required_artifacts"), list) else closure_audit.get("required_artifacts", [])
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-final-audit-rollup.v1",
            "rollup_kind": "source-map-terminal-review-final-audit",
            "selected_consumer": str(closure.get("selected_consumer") or ""),
            "selected_action_id": str(closure.get("selected_action_id") or ""),
            "application_surface": str(closure.get("application_surface") or ""),
            "closure_status": str(closure.get("closure_status") or ""),
            "final_audit_status": final_status,
            "terminal_review_candidate": bool(closure.get("terminal_review_candidate")) and not blocked,
            "followup_required": bool(closure.get("followup_required")) and not blocked,
            "recommended_review_action": str(closure.get("recommended_review_action") or closure_audit.get("recommended_review_action") or ""),
            "observed_review_action": str(closure.get("observed_review_action") or closure_audit.get("observed_review_action") or ""),
            "required_artifacts": required_artifacts,
            "required_artifact_count": len(required_artifacts) if isinstance(required_artifacts, list) else 0,
            "closure_checkpoint_digest_sha256": closure_digest,
            "terminal_review_package_digest_sha256": str(closure.get("source_terminal_review_package_digest_sha256") or package_digest),
            "observed_result_digest_sha256": str(closure.get("source_observed_result_digest_sha256") or closure_audit.get("observed_result_digest_sha256") or ""),
            "manual_review_observed": bool(closure.get("observed_review_completed") or closure_audit.get("manual_review_observed")) and not blocked,
            "execute_recommended_action": False,
            "final_review_required": True,
        }

    @staticmethod
    def _warnings(closure: dict[str, Any]) -> list[str]:
        warnings = ["source_map_terminal_review_final_audit_does_not_execute_recommended_action"]
        if closure:
            warnings.append("source_map_terminal_review_final_audit_requires_manual_review")
        if closure.get("followup_required") is True:
            warnings.append("source_map_terminal_review_final_audit_followup_observed")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if any(item == "source_map_terminal_review_closure_checkpoint_missing" for item in blockers):
            return "provide_source_map_terminal_review_closure_checkpoint"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_terminal_review_final_audit_inputs"
        if blockers:
            return "inspect_source_map_terminal_review_final_audit_failure"
        return "review_source_map_terminal_review_final_audit"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughCompletionCheckpointManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "audit_rollup_only": True,
            "final_audit_only": True,
            "closure_summary_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "recommended_action_executed_by_rollup": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "delivery_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughChainReadinessSpec:
    """Read-only Source Map follow-through chain readiness descriptor.

    This descriptor is an orchestrator map, not an executor.  It consumes any
    subset of the Source Map review / approval / application artifacts and
    reports the furthest proven stage plus the next explicit review action.  It
    never starts browsers, sends CDP commands, installs hooks/logpoints, fetches
    Source Maps, writes rebuild bundles, records approvals, or calls MCP.
    """

    source_map_readiness: dict[str, Any] = field(default_factory=dict)
    source_map_consumer_action_plan: dict[str, Any] = field(default_factory=dict)
    source_map_consumer_materialization: dict[str, Any] = field(default_factory=dict)
    source_map_typed_payload_preflight: dict[str, Any] = field(default_factory=dict)
    source_map_followthrough_review: dict[str, Any] = field(default_factory=dict)
    source_map_followthrough_surface_selection: dict[str, Any] = field(default_factory=dict)
    source_map_selected_executor_input_review: dict[str, Any] = field(default_factory=dict)
    source_map_selected_executor_approval_plan: dict[str, Any] = field(default_factory=dict)
    source_map_selected_executor_approval_record: dict[str, Any] = field(default_factory=dict)
    source_map_selected_executor_apply_preflight: dict[str, Any] = field(default_factory=dict)
    source_map_debugger_candidates: dict[str, Any] = field(default_factory=dict)
    source_map_debugger_candidate_selection: dict[str, Any] = field(default_factory=dict)
    source_map_hook_candidates: dict[str, Any] = field(default_factory=dict)
    source_map_hook_candidate_selection: dict[str, Any] = field(default_factory=dict)
    source_map_source_logpoint_install_result: dict[str, Any] = field(default_factory=dict)
    source_map_debugger_execution_result: dict[str, Any] = field(default_factory=dict)
    source_map_hook_install_result: dict[str, Any] = field(default_factory=dict)
    source_map_rebuild_result: dict[str, Any] = field(default_factory=dict)
    source_map_rebuild_generation_result: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughChainReadinessSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_chain_readiness",
                "sourceMapFollowthroughChainReadiness",
                "source_map_followthrough_chain_review",
                "sourceMapFollowthroughChainReview",
                "source_map_followthrough_status",
                "sourceMapFollowthroughStatus",
                "source_map_chain_readiness",
                "sourceMapChainReadiness",
            )
        )
        kwargs = {
            "source_map_readiness": cls._object_alias(context, "source_map_readiness", "source-map-readiness", "sourceMapReadiness"),
            "source_map_consumer_action_plan": cls._object_alias(context, "source_map_consumer_action_plan", "source-map-consumer-action-plan", "sourceMapConsumerActionPlan"),
            "source_map_consumer_materialization": cls._object_alias(context, "source_map_consumer_materialization", "source-map-consumer-materialization", "sourceMapConsumerMaterialization"),
            "source_map_typed_payload_preflight": cls._object_alias(context, "source_map_typed_payload_preflight", "source-map-typed-payload-preflight", "sourceMapTypedPayloadPreflight"),
            "source_map_followthrough_review": cls._object_alias(context, "source_map_followthrough_review", "source-map-followthrough-review", "sourceMapFollowthroughReview"),
            "source_map_followthrough_surface_selection": cls._object_alias(context, "source_map_followthrough_surface_selection", "source-map-followthrough-surface-selection", "sourceMapFollowthroughSurfaceSelection"),
            "source_map_selected_executor_input_review": cls._object_alias(context, "source_map_selected_executor_input_review", "source-map-selected-executor-input-review", "sourceMapSelectedExecutorInputReview"),
            "source_map_selected_executor_approval_plan": cls._object_alias(context, "source_map_selected_executor_approval_plan", "source-map-selected-executor-approval-plan", "sourceMapSelectedExecutorApprovalPlan"),
            "source_map_selected_executor_approval_record": cls._object_alias(context, "source_map_selected_executor_approval_record", "source-map-selected-executor-approval-record", "sourceMapSelectedExecutorApprovalRecord"),
            "source_map_selected_executor_apply_preflight": cls._object_alias(context, "source_map_selected_executor_apply_preflight", "source-map-selected-executor-apply-preflight", "sourceMapSelectedExecutorApplyPreflight"),
            "source_map_debugger_candidates": cls._object_alias(context, "source_map_debugger_candidates", "source-map-debugger-candidates", "sourceMapDebuggerCandidates"),
            "source_map_debugger_candidate_selection": cls._object_alias(context, "source_map_debugger_candidate_selection", "source-map-debugger-candidate-selection", "sourceMapDebuggerCandidateSelection"),
            "source_map_hook_candidates": cls._object_alias(context, "source_map_hook_candidates", "source-map-hook-candidates", "sourceMapHookCandidates"),
            "source_map_hook_candidate_selection": cls._object_alias(context, "source_map_hook_candidate_selection", "source-map-hook-candidate-selection", "sourceMapHookCandidateSelection"),
            "source_map_source_logpoint_install_result": cls._object_alias(context, "source_map_source_logpoint_install_result", "source-map-source-logpoint-install-result", "sourceMapSourceLogpointInstallResult"),
            "source_map_debugger_execution_result": cls._object_alias(context, "source_map_debugger_execution_result", "source-map-debugger-execution-result", "sourceMapDebuggerExecutionResult"),
            "source_map_hook_install_result": cls._object_alias(context, "source_map_hook_install_result", "source-map-hook-install-result", "sourceMapHookInstallResult"),
            "source_map_rebuild_result": cls._object_alias(context, "source_map_rebuild_result", "source-map-rebuild-result", "sourceMapRebuildResult"),
            "source_map_rebuild_generation_result": cls._object_alias(context, "source_map_rebuild_generation_result", "source-map-rebuild-generation-result", "sourceMapRebuildGenerationResult"),
        }
        if not requested and not any(kwargs.values()):
            return None
        return cls(
            **kwargs,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughChainReadinessResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapFollowthroughChainReadinessManager:
    """Review-only Source Map follow-through chain state normalizer."""

    _STAGES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
        ("source_map_readiness", "workspace/source-map-readiness.json", "review_source_map_readiness", ("reverse-deepagent.source-map-readiness.v1",)),
        ("source_map_consumer_action_plan", "workspace/source-map-consumer-action-plan.json", "review_source_map_consumer_action_plan", ("reverse-deepagent.source-map-consumer-action-plan.v1",)),
        ("source_map_consumer_materialization", "workspace/source-map-consumer-materialization.json", "review_source_map_consumer_materialization", ("reverse-deepagent.source-map-consumer-materialization.v1",)),
        ("source_map_typed_payload_preflight", "workspace/source-map-typed-payload-preflight.json", "review_source_map_typed_payload_preflight", ("reverse-deepagent.source-map-typed-payload-preflight.v1",)),
        ("source_map_followthrough_review", "workspace/source-map-followthrough-review.json", "review_source_map_followthrough_review", ("reverse-deepagent.source-map-followthrough-review.v1",)),
        ("source_map_followthrough_surface_selection", "workspace/source-map-followthrough-surface-selection.json", "select_source_map_followthrough_surface", ("reverse-deepagent.source-map-followthrough-surface-selection.v1",)),
        ("source_map_selected_executor_input_review", "workspace/source-map-selected-executor-input-review.json", "review_source_map_selected_executor_input", ("reverse-deepagent.source-map-selected-executor-input-review.v1",)),
        ("source_map_selected_executor_approval_plan", "workspace/source-map-selected-executor-approval-plan.json", "review_source_map_selected_executor_approval_plan", ("reverse-deepagent.source-map-selected-executor-approval-plan.v1",)),
        ("source_map_selected_executor_approval_record", "workspace/source-map-selected-executor-approval-record.json", "record_source_map_selected_executor_approval", ("reverse-deepagent.source-map-selected-executor-approval-record.v1",)),
        ("source_map_selected_executor_apply_preflight", "workspace/source-map-selected-executor-apply-preflight.json", "review_source_map_selected_executor_apply_preflight", ("reverse-deepagent.source-map-selected-executor-apply-preflight.v1",)),
    )
    _RESULTS: dict[str, tuple[str, str]] = {
        "debugger": ("source_map_debugger_execution_result", "workspace/source-map-debugger-execution-result.json"),
        "source-logpoint": ("source_map_source_logpoint_install_result", "workspace/source-map-source-logpoint-install-result.json"),
        "hook": ("source_map_hook_install_result", "workspace/source-map-hook-install-result.json"),
        "rebuild": ("source_map_rebuild_generation_result", "workspace/source-map-rebuild-generation-result.json"),
        "rebuild-metadata": ("source_map_rebuild_result", "workspace/source-map-rebuild-result.json"),
    }

    def review(self, spec: SourceMapFollowthroughChainReadinessSpec | None) -> SourceMapFollowthroughChainReadinessResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughChainReadinessResult(status="unsupported", reason="missing_source_map_followthrough_chain_readiness_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughChainReadinessResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_chain_readiness_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughChainReadinessResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_chain_readiness_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughChainReadinessSpec) -> dict[str, Any]:
        artifacts = self._artifact_map(spec)
        stage_statuses = [self._stage_status(name, path, next_action, schemas, artifacts.get(name, {})) for name, path, next_action, schemas in self._STAGES]
        candidate_statuses = self._candidate_statuses(artifacts)
        selected_consumer = self._selected_consumer(spec, artifacts)
        result_statuses = self._result_statuses(artifacts, selected_consumer)
        blockers = self._blockers(stage_statuses, candidate_statuses, result_statuses)
        completed_stage = self._completed_stage(stage_statuses)
        next_stage = self._next_stage(stage_statuses)
        selected_result = result_statuses.get(selected_consumer) if selected_consumer else None
        selected_executor_result_ready = bool(selected_result and selected_result.get("ready"))
        warnings = self._warnings(spec, stage_statuses, candidate_statuses, result_statuses, selected_consumer)
        if not any(status["present"] for status in stage_statuses) and not any(status["present"] for status in candidate_statuses.values()) and not any(status["present"] for status in result_statuses.values()):
            blockers.append("source_map_followthrough_chain_evidence_missing")
        status = "blocked" if blockers else "ready_for_review"
        next_action = self._next_action(blockers, next_stage, selected_consumer, selected_executor_result_ready)
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-chain-readiness.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "readiness_descriptor_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer,
            "selected_consumer": selected_consumer,
            "completed_stage": completed_stage,
            "next_stage": next_stage["stage"] if next_stage else "selected_executor_result_review" if not selected_executor_result_ready else "inspect_selected_executor_result",
            "next_required_artifact": next_stage["artifact"] if next_stage else self._selected_result_artifact(selected_consumer),
            "next_required_action": next_action,
            "stage_statuses": stage_statuses,
            "candidate_statuses": candidate_statuses,
            "result_statuses": result_statuses,
            "missing_required_artifacts": [stage["artifact"] for stage in stage_statuses if not stage["present"]],
            "blocked_stage_names": [stage["stage"] for stage in stage_statuses if stage["present"] and not stage["ready"]],
            "ready_for_selected_executor_review": self._ready_bool(artifacts.get("source_map_selected_executor_apply_preflight", {}), "ready_for_selected_executor_review"),
            "selected_executor_result_ready": selected_executor_result_ready,
            "automatic_followthrough_supported": False,
            "automatic_debugger_continuation_supported": False,
            "automatic_hook_install_supported": False,
            "automatic_source_logpoint_install_supported": False,
            "automatic_raw_source_rebuild_supported": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "source_map_fetched": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "hook_installed": False,
            "logpoint_installed": False,
            "debugger_executed": False,
            "rebuild_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": next_action,
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-chain-readiness.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "readiness_descriptor_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "reason": reason,
            "selected_consumer": "",
            "completed_stage": "",
            "next_stage": "source_map_readiness",
            "next_required_artifact": "workspace/source-map-readiness.json",
            "next_required_action": "review_source_map_readiness",
            "stage_statuses": [],
            "candidate_statuses": {},
            "result_statuses": {},
            "missing_required_artifacts": [],
            "blocked_stage_names": [],
            "ready_for_selected_executor_review": False,
            "selected_executor_result_ready": False,
            "automatic_followthrough_supported": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_followthrough_chain_evidence",
            "side_effect_policy": self._side_effect_policy(),
        }

    @staticmethod
    def _artifact_map(spec: SourceMapFollowthroughChainReadinessSpec) -> dict[str, dict[str, Any]]:
        return {
            "source_map_readiness": spec.source_map_readiness,
            "source_map_consumer_action_plan": spec.source_map_consumer_action_plan,
            "source_map_consumer_materialization": spec.source_map_consumer_materialization,
            "source_map_typed_payload_preflight": spec.source_map_typed_payload_preflight,
            "source_map_followthrough_review": spec.source_map_followthrough_review,
            "source_map_followthrough_surface_selection": spec.source_map_followthrough_surface_selection,
            "source_map_selected_executor_input_review": spec.source_map_selected_executor_input_review,
            "source_map_selected_executor_approval_plan": spec.source_map_selected_executor_approval_plan,
            "source_map_selected_executor_approval_record": spec.source_map_selected_executor_approval_record,
            "source_map_selected_executor_apply_preflight": spec.source_map_selected_executor_apply_preflight,
            "source_map_debugger_candidates": spec.source_map_debugger_candidates,
            "source_map_debugger_candidate_selection": spec.source_map_debugger_candidate_selection,
            "source_map_hook_candidates": spec.source_map_hook_candidates,
            "source_map_hook_candidate_selection": spec.source_map_hook_candidate_selection,
            "source_map_source_logpoint_install_result": spec.source_map_source_logpoint_install_result,
            "source_map_debugger_execution_result": spec.source_map_debugger_execution_result,
            "source_map_hook_install_result": spec.source_map_hook_install_result,
            "source_map_rebuild_result": spec.source_map_rebuild_result,
            "source_map_rebuild_generation_result": spec.source_map_rebuild_generation_result,
        }

    @classmethod
    def _stage_status(cls, name: str, artifact: str, next_action: str, schemas: tuple[str, ...], descriptor: dict[str, Any]) -> dict[str, Any]:
        present = bool(descriptor)
        status = cls._status(descriptor)
        blockers = cls._string_list(descriptor.get("blockers")) if present else []
        ready = False
        if present:
            schema_ok = descriptor.get("schema_version") in {None, "", *schemas}
            failed = status in {"blocked", "failed", "failure", "error", "unsupported"}
            ready = bool(schema_ok and not failed and not blockers and cls._readiness_gate(name, descriptor))
        return {
            "stage": name,
            "artifact": artifact,
            "present": present,
            "schema_version": str(descriptor.get("schema_version") or "") if present else "",
            "status": status,
            "ready": ready,
            "blockers": blockers,
            "next_action": next_action,
            "side_effect_safe": not cls._side_effect_blockers(descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}, prefix=name) if present else True,
        }

    @classmethod
    def _candidate_statuses(cls, artifacts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        entries = {
            "debugger_candidates": ("source_map_debugger_candidates", "workspace/source-map-debugger-candidates.json", "review_source_map_debugger_candidates"),
            "debugger_candidate_selection": ("source_map_debugger_candidate_selection", "workspace/source-map-debugger-candidate-selection.json", "review_source_map_debugger_candidate_selection"),
            "hook_candidates": ("source_map_hook_candidates", "workspace/source-map-hook-candidates.json", "review_source_map_hook_candidates"),
            "hook_candidate_selection": ("source_map_hook_candidate_selection", "workspace/source-map-hook-candidate-selection.json", "review_source_map_hook_candidate_selection"),
        }
        result: dict[str, dict[str, Any]] = {}
        for label, (key, artifact, action) in entries.items():
            descriptor = artifacts.get(key, {})
            present = bool(descriptor)
            status = cls._status(descriptor)
            blockers = cls._string_list(descriptor.get("blockers")) if present else []
            result[label] = {
                "artifact_key": key,
                "artifact": artifact,
                "present": present,
                "schema_version": str(descriptor.get("schema_version") or "") if present else "",
                "status": status,
                "ready": bool(present and status not in {"blocked", "failed", "failure", "error", "unsupported"} and not blockers),
                "selected_candidate_id": str(descriptor.get("selected_candidate_id") or ""),
                "next_action": action,
                "blockers": blockers,
            }
        return result

    @classmethod
    def _result_statuses(cls, artifacts: dict[str, dict[str, Any]], selected_consumer: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for consumer, (key, artifact) in cls._RESULTS.items():
            descriptor = artifacts.get(key, {})
            present = bool(descriptor)
            status = cls._status(descriptor)
            blockers = cls._string_list(descriptor.get("blockers")) if present else []
            ready = bool(present and status in {"success", "ready_for_review", "written", "completed", "partial"} and not blockers)
            result[consumer] = {
                "artifact_key": key,
                "artifact": artifact,
                "present": present,
                "status": status,
                "ready": ready,
                "selected": bool(selected_consumer == consumer or (selected_consumer == "rebuild" and consumer in {"rebuild", "rebuild-metadata"})),
                "blockers": blockers,
            }
        return result

    @staticmethod
    def _readiness_gate(stage: str, descriptor: dict[str, Any]) -> bool:
        gates = {
            "source_map_readiness": ("debugger_planning_ready", "rebuild_planning_ready", "source_logpoint_planning_ready", "hook_planning_ready"),
            "source_map_consumer_action_plan": ("ready_action_count",),
            "source_map_consumer_materialization": ("typed_review_payload_count",),
            "source_map_typed_payload_preflight": ("ready_for_followthrough_review",),
            "source_map_followthrough_review": ("ready_for_explicit_review",),
            "source_map_followthrough_surface_selection": ("ready_for_surface_review",),
            "source_map_selected_executor_input_review": ("ready_for_executor_review",),
            "source_map_selected_executor_approval_plan": ("apply_plan_ready_for_review",),
            "source_map_selected_executor_approval_record": ("approval_recorded", "approved_for_apply"),
            "source_map_selected_executor_apply_preflight": ("ready_for_selected_executor_review", "executor_input_ready"),
        }
        keys = gates.get(stage, ())
        if not keys:
            return True
        if stage == "source_map_readiness":
            return any(bool(descriptor.get(key)) for key in keys)
        return all(bool(descriptor.get(key)) for key in keys)

    @classmethod
    def _blockers(cls, stages: list[dict[str, Any]], candidates: dict[str, dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        for stage in stages:
            if stage["present"] and not stage["ready"]:
                blockers.append(f"{stage['stage']}_not_ready")
                blockers.extend(f"{stage['stage']}:{item}" for item in stage.get("blockers", []))
        for label, status in candidates.items():
            if status["present"] and not status["ready"]:
                blockers.append(f"{label}_not_ready")
                blockers.extend(f"{label}:{item}" for item in status.get("blockers", []))
        for label, status in results.items():
            if status["present"] and not status["ready"]:
                blockers.append(f"{label}_result_not_ready")
                blockers.extend(f"{label}_result:{item}" for item in status.get("blockers", []))
        return blockers

    @staticmethod
    def _completed_stage(stages: list[dict[str, Any]]) -> str:
        completed = ""
        for stage in stages:
            if stage["ready"]:
                completed = str(stage["stage"])
        return completed

    @staticmethod
    def _next_stage(stages: list[dict[str, Any]]) -> dict[str, Any] | None:
        last_ready_index = -1
        for index, stage in enumerate(stages):
            if stage["ready"]:
                last_ready_index = index
        for stage in stages[last_ready_index + 1 :]:
            if not stage["ready"]:
                return stage
        return None

    @staticmethod
    def _ready_bool(descriptor: dict[str, Any], key: str) -> bool:
        return bool(descriptor.get(key)) if isinstance(descriptor, dict) else False

    @classmethod
    def _selected_consumer(cls, spec: SourceMapFollowthroughChainReadinessSpec, artifacts: dict[str, dict[str, Any]]) -> str:
        for descriptor_key, keys in (
            ("source_map_selected_executor_apply_preflight", ("selected_consumer",)),
            ("source_map_selected_executor_approval_plan", ("selected_consumer",)),
            ("source_map_selected_executor_input_review", ("selected_consumer",)),
            ("source_map_followthrough_surface_selection", ("selected_consumer",)),
            ("source_map_hook_candidate_selection", ("selected_consumer",)),
            ("source_map_debugger_candidate_selection", ("selected_consumer",)),
        ):
            descriptor = artifacts.get(descriptor_key, {})
            for key in keys:
                value = str(descriptor.get(key) or "") if isinstance(descriptor, dict) else ""
                if value:
                    return cls._normalize_consumer(value)
        return cls._normalize_consumer(spec.expected_consumer)

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        normalized = value.strip().replace("_", "-").lower()
        aliases = {"source-logpoints": "source-logpoint", "logpoint": "source-logpoint", "logpoints": "source-logpoint", "rebuild-metadata": "rebuild"}
        return aliases.get(normalized, normalized)

    @classmethod
    def _selected_result_artifact(cls, consumer: str) -> str:
        if consumer in cls._RESULTS:
            return cls._RESULTS[consumer][1]
        return "workspace/source-map-selected-executor-result.json"

    @staticmethod
    def _warnings(spec: SourceMapFollowthroughChainReadinessSpec, stages: list[dict[str, Any]], candidates: dict[str, dict[str, Any]], results: dict[str, dict[str, Any]], selected_consumer: str) -> list[str]:
        warnings: list[str] = [
            "source_map_followthrough_chain_readiness_is_not_an_executor",
            "automatic_source_map_followthrough_remains_disabled",
            "explicit_review_required_for_any_executor_application",
        ]
        if selected_consumer in {"debugger", "hook"}:
            key = f"{selected_consumer}_candidate_selection"
            if not candidates.get(key, {}).get("present"):
                warnings.append(f"{selected_consumer}_candidate_selection_not_provided")
        if any(stage["ready"] for stage in stages) and not any(status["selected"] and status["ready"] for status in results.values()):
            warnings.append("selected_executor_result_not_observed")
        if spec.expected_consumer and selected_consumer and SourceMapFollowthroughChainReadinessManager._normalize_consumer(spec.expected_consumer) != selected_consumer:
            warnings.append("expected_consumer_differs_from_selected_consumer")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], next_stage: dict[str, Any] | None, selected_consumer: str, selected_executor_result_ready: bool) -> str:
        if blockers:
            if "source_map_followthrough_chain_evidence_missing" in blockers:
                return "provide_source_map_followthrough_chain_evidence"
            return "resolve_source_map_followthrough_chain_readiness_blockers"
        if next_stage is not None:
            return str(next_stage.get("next_action") or "review_source_map_followthrough_chain_inputs")
        if selected_executor_result_ready:
            return "inspect_selected_source_map_executor_result_and_decide_followup"
        return {
            "debugger": "review_source_map_debugger_executor_application",
            "source-logpoint": "review_source_map_source_logpoint_executor_application",
            "hook": "review_source_map_hook_executor_application",
            "rebuild": "review_source_map_rebuild_generation_or_metadata_result",
        }.get(selected_consumer, "review_selected_source_map_executor_application")

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "readiness_descriptor_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughOneStepPlanSpec:
    """Review-only one-step Source Map follow-through orchestration plan.

    This consumes the chain readiness descriptor and packages exactly one next
    explicit review action for a human / agent reviewer.  It does not invoke the
    next protection, execute any runtime action, or record approval.
    """

    source_map_followthrough_chain_readiness: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_next_action: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughOneStepPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_one_step_plan",
                "sourceMapFollowthroughOneStepPlan",
                "source_map_followthrough_orchestrator_plan",
                "sourceMapFollowthroughOrchestratorPlan",
                "source_map_followthrough_next_step_plan",
                "sourceMapFollowthroughNextStepPlan",
            )
        )
        chain = cls._object_alias(
            context,
            "source_map_followthrough_chain_readiness",
            "source-map-followthrough-chain-readiness",
            "sourceMapFollowthroughChainReadiness",
            "source_map_followthrough_chain_review",
            "source-map-followthrough-chain-review",
            "sourceMapFollowthroughChainReview",
            "source_map_followthrough_status",
            "source-map-followthrough-status",
            "sourceMapFollowthroughStatus",
        )
        if not requested and not chain:
            return None
        return cls(
            source_map_followthrough_chain_readiness=chain,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_next_action=str(context.get("expected_next_action", context.get("expectedNextAction", context.get("source_map_next_action", context.get("sourceMapNextAction", "")))) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughOneStepPlanResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapFollowthroughOneStepPlanManager:
    """Plan exactly one reviewed Source Map follow-through next step."""

    def review(self, spec: SourceMapFollowthroughOneStepPlanSpec | None) -> SourceMapFollowthroughOneStepPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughOneStepPlanResult(status="unsupported", reason="missing_source_map_followthrough_one_step_plan_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughOneStepPlanResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_one_step_plan_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughOneStepPlanResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_one_step_plan_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughOneStepPlanSpec) -> dict[str, Any]:
        chain = spec.source_map_followthrough_chain_readiness
        blockers = self._chain_blockers(chain)
        blockers.extend(self._expectation_blockers(spec, chain))
        planned_step = {} if blockers else self._planned_step(chain, spec)
        blockers.extend(self._planned_step_blockers(planned_step))
        warnings = self._warnings(chain, planned_step)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-one-step-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "one_step_plan_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "source_chain_readiness_schema_version": str(chain.get("schema_version") or ""),
            "source_chain_readiness_status": self._status(chain),
            "source_chain_completed_stage": str(chain.get("completed_stage") or ""),
            "source_chain_next_stage": str(chain.get("next_stage") or ""),
            "source_chain_next_required_artifact": str(chain.get("next_required_artifact") or ""),
            "source_chain_next_action": str(chain.get("next_action") or chain.get("next_required_action") or ""),
            "selected_consumer": str(chain.get("selected_consumer") or ""),
            "expected_consumer": spec.expected_consumer,
            "expected_next_action": spec.expected_next_action,
            "reviewer": spec.reviewer,
            "planned_step": planned_step,
            "planned_step_ready_for_review": bool(planned_step) and not blockers,
            "will_invoke_next_action": False,
            "will_record_approval": False,
            "will_run_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers, planned_step),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-one-step-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "one_step_plan_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_chain_readiness_schema_version": "",
            "source_chain_readiness_status": "",
            "source_chain_completed_stage": "",
            "source_chain_next_stage": "",
            "source_chain_next_required_artifact": "",
            "source_chain_next_action": "",
            "selected_consumer": "",
            "expected_consumer": "",
            "expected_next_action": "",
            "reviewer": "",
            "planned_step": {},
            "planned_step_ready_for_review": False,
            "will_invoke_next_action": False,
            "will_record_approval": False,
            "will_run_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_chain_readiness_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _chain_blockers(cls, chain: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not chain:
            return ["source_map_followthrough_chain_readiness_missing"]
        if chain.get("schema_version") not in {None, "", "reverse-deepagent.source-map-followthrough-chain-readiness.v1"}:
            blockers.append("source_map_followthrough_chain_readiness_schema_mismatch")
        if cls._status(chain) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_chain_readiness_not_ready")
        blockers.extend(f"source_map_followthrough_chain_readiness:{item}" for item in cls._string_list(chain.get("blockers")))
        if not str(chain.get("next_action") or chain.get("next_required_action") or ""):
            blockers.append("source_map_followthrough_chain_next_action_missing")
        if not str(chain.get("next_required_artifact") or ""):
            blockers.append("source_map_followthrough_chain_next_required_artifact_missing")
        if bool(chain.get("automatic_followthrough_supported")) or bool(chain.get("automatic_execution_supported")):
            blockers.append("source_map_followthrough_chain_automatic_execution_claim_detected")
        policy = chain.get("side_effect_policy") if isinstance(chain.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_followthrough_chain_readiness"))
        return blockers

    @classmethod
    def _expectation_blockers(cls, spec: SourceMapFollowthroughOneStepPlanSpec, chain: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        selected_consumer = cls._normalize_consumer(str(chain.get("selected_consumer") or ""))
        expected_consumer = cls._normalize_consumer(spec.expected_consumer)
        next_action = str(chain.get("next_action") or chain.get("next_required_action") or "")
        if expected_consumer and selected_consumer and expected_consumer != selected_consumer:
            blockers.append("source_map_followthrough_one_step_consumer_mismatch")
        if spec.expected_next_action and next_action and spec.expected_next_action != next_action:
            blockers.append("source_map_followthrough_one_step_next_action_mismatch")
        return blockers

    @classmethod
    def _planned_step(cls, chain: dict[str, Any], spec: SourceMapFollowthroughOneStepPlanSpec) -> dict[str, Any]:
        selected_consumer = cls._normalize_consumer(str(chain.get("selected_consumer") or spec.expected_consumer or ""))
        next_stage = str(chain.get("next_stage") or "")
        next_action = str(chain.get("next_action") or chain.get("next_required_action") or "")
        required_artifact = str(chain.get("next_required_artifact") or "")
        return {
            "step_id": cls._step_id(selected_consumer, next_stage, next_action, required_artifact),
            "step_schema_version": "reverse-deepagent.source-map-followthrough-one-step.v1",
            "selected_consumer": selected_consumer,
            "completed_stage": str(chain.get("completed_stage") or ""),
            "next_stage": next_stage,
            "next_action": next_action,
            "next_required_artifact": required_artifact,
            "review_prompt": cls._review_prompt(selected_consumer, next_stage, next_action),
            "requires_explicit_review": True,
            "requires_separate_executor_call": True,
            "execute_automatically": False,
            "executor_invoked": False,
            "approval_recorded": False,
            "apply_preflight_invoked": False,
            "result_artifact_observed": bool(chain.get("selected_executor_result_ready")),
            "source_chain_digest_sha256": cls._stable_json_digest(chain),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _planned_step_blockers(planned_step: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not planned_step:
            return blockers
        if planned_step.get("requires_explicit_review") is not True:
            blockers.append("source_map_followthrough_one_step_review_gate_missing")
        if planned_step.get("execute_automatically") is True or planned_step.get("executor_invoked") is True:
            blockers.append("source_map_followthrough_one_step_execution_claim_detected")
        if not planned_step.get("next_action"):
            blockers.append("source_map_followthrough_one_step_next_action_missing")
        if not planned_step.get("next_required_artifact"):
            blockers.append("source_map_followthrough_one_step_next_artifact_missing")
        return blockers

    @staticmethod
    def _warnings(chain: dict[str, Any], planned_step: dict[str, Any]) -> list[str]:
        warnings = [
            "source_map_followthrough_one_step_plan_is_not_an_executor",
            "separate_explicit_review_required_before_any_runtime_action",
        ]
        if planned_step.get("result_artifact_observed"):
            warnings.append("selected_executor_result_already_observed_review_before_replanning")
        if chain.get("missing_required_artifacts"):
            warnings.append("source_map_followthrough_chain_has_missing_historical_artifacts")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], planned_step: dict[str, Any]) -> str:
        if blockers:
            if any(item.startswith("source_map_followthrough_chain_readiness") for item in blockers):
                return "provide_ready_source_map_followthrough_chain_readiness_descriptor"
            return "resolve_source_map_followthrough_one_step_plan_blockers"
        return "review_source_map_followthrough_one_step_plan_before_next_action"

    @staticmethod
    def _review_prompt(consumer: str, next_stage: str, next_action: str) -> str:
        consumer_label = consumer or "selected Source Map consumer"
        return f"Review one Source Map follow-through step for {consumer_label}: {next_stage or 'next stage'} via {next_action}."

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        normalized = value.strip().replace("_", "-").lower()
        aliases = {"source-logpoints": "source-logpoint", "logpoint": "source-logpoint", "logpoints": "source-logpoint", "rebuild-metadata": "rebuild"}
        return aliases.get(normalized, normalized)

    @staticmethod
    def _step_id(consumer: str, next_stage: str, next_action: str, required_artifact: str) -> str:
        seed = {"consumer": consumer, "next_stage": next_stage, "next_action": next_action, "next_required_artifact": required_artifact}
        digest = hashlib.sha256(json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
        return f"source-map-followthrough-one-step:{digest}"

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "one_step_plan_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "apply_preflight_invoked": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughDispatchPreflightSpec:
    """Read-only preflight for one reviewed Source Map follow-through dispatch.

    The descriptor consumes a ready one-step plan and verifies that the planned
    next action maps to a known explicit review / executor surface.  It does not
    call that surface, record approval, run apply preflight, or execute runtime
    actions.
    """

    source_map_followthrough_one_step_plan: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_next_action: str = ""
    expected_required_artifact: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughDispatchPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_dispatch_preflight",
                "sourceMapFollowthroughDispatchPreflight",
                "source_map_followthrough_dispatch_review",
                "sourceMapFollowthroughDispatchReview",
                "source_map_followthrough_executor_dispatch_preflight",
                "sourceMapFollowthroughExecutorDispatchPreflight",
            )
        )
        one_step_plan = cls._object_alias(
            context,
            "source_map_followthrough_one_step_plan",
            "source-map-followthrough-one-step-plan",
            "sourceMapFollowthroughOneStepPlan",
            "source_map_followthrough_orchestrator_plan",
            "source-map-followthrough-orchestrator-plan",
            "sourceMapFollowthroughOrchestratorPlan",
            "source_map_followthrough_next_step_plan",
            "source-map-followthrough-next-step-plan",
            "sourceMapFollowthroughNextStepPlan",
        )
        if not requested and not one_step_plan:
            return None
        return cls(
            source_map_followthrough_one_step_plan=one_step_plan,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", "")) or ""),
            expected_next_action=str(context.get("expected_next_action", context.get("expectedNextAction", "")) or ""),
            expected_required_artifact=str(context.get("expected_required_artifact", context.get("expectedRequiredArtifact", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughDispatchPreflightResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapFollowthroughDispatchPreflightManager:
    """Preflight one reviewed Source Map follow-through dispatch target."""

    _DISPATCH_TARGETS: dict[str, dict[str, str]] = {
        "debugger": {
            "consumer": "debugger",
            "next_action": "review_source_map_debugger_executor_application",
            "dispatch_surface": "source-map-debugger-execution-result",
            "result_artifact": "workspace/source-map-debugger-execution-result.json",
            "review_gate": "explicit_source_map_debugger_executor_review",
        },
        "source-logpoint": {
            "consumer": "source-logpoint",
            "next_action": "review_source_map_source_logpoint_executor_application",
            "dispatch_surface": "source-map-source-logpoint-install-result",
            "result_artifact": "workspace/source-map-source-logpoint-install-result.json",
            "review_gate": "explicit_source_map_source_logpoint_install_review",
        },
        "hook": {
            "consumer": "hook",
            "next_action": "review_source_map_hook_executor_application",
            "dispatch_surface": "source-map-hook-install-result",
            "result_artifact": "workspace/source-map-hook-install-result.json",
            "review_gate": "explicit_source_map_hook_install_review",
        },
        "rebuild": {
            "consumer": "rebuild",
            "next_action": "review_source_map_rebuild_executor_application",
            "dispatch_surface": "source-map-rebuild-generation-result",
            "result_artifact": "workspace/source-map-rebuild-generation-result.json",
            "review_gate": "explicit_source_map_rebuild_generation_review",
        },
    }

    _ACTION_ALIASES: dict[str, str] = {
        "review_source_map_debugger_executor_application": "debugger",
        "review_source_map_source_logpoint_executor_application": "source-logpoint",
        "install_reviewed_source_map_source_logpoint": "source-logpoint",
        "review_source_map_hook_executor_application": "hook",
        "review_source_map_rebuild_executor_application": "rebuild",
        "review_source_map_rebuild_generation_or_metadata_result": "rebuild",
        "run_reviewed_source_map_rebuild_metadata_generation": "rebuild",
        "generate_reviewed_source_map_rebuild_bundle": "rebuild",
    }

    def review(self, spec: SourceMapFollowthroughDispatchPreflightSpec | None) -> SourceMapFollowthroughDispatchPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughDispatchPreflightResult(status="unsupported", reason="missing_source_map_followthrough_dispatch_preflight_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughDispatchPreflightResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_dispatch_preflight_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughDispatchPreflightResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_dispatch_preflight_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughDispatchPreflightSpec) -> dict[str, Any]:
        plan = spec.source_map_followthrough_one_step_plan
        planned_step = plan.get("planned_step") if isinstance(plan.get("planned_step"), dict) else {}
        selected_consumer = self._normalize_consumer(str(planned_step.get("selected_consumer") or plan.get("selected_consumer") or spec.expected_consumer or ""))
        next_action = str(planned_step.get("next_action") or plan.get("source_chain_next_action") or spec.expected_next_action or "")
        required_artifact = str(planned_step.get("next_required_artifact") or plan.get("source_chain_next_required_artifact") or spec.expected_required_artifact or "")
        action_consumer = self._ACTION_ALIASES.get(next_action, selected_consumer)
        dispatch_target = self._DISPATCH_TARGETS.get(action_consumer, {})
        blockers = self._plan_blockers(plan, planned_step)
        blockers.extend(self._expectation_blockers(spec, selected_consumer, next_action, required_artifact))
        blockers.extend(self._dispatch_blockers(selected_consumer, next_action, required_artifact, dispatch_target))
        dispatcher_input = {} if blockers else self._dispatcher_input(plan, planned_step, dispatch_target, spec)
        warnings = self._warnings(plan, dispatcher_input)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-preflight.v1",
            "status": status,
            "review_only": True,
            "preflight_only": True,
            "plan_only": True,
            "dispatch_preflight_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "source_one_step_plan_schema_version": str(plan.get("schema_version") or ""),
            "source_one_step_plan_status": self._status(plan),
            "source_one_step_plan_digest_sha256": self._stable_json_digest(plan) if plan else "",
            "selected_consumer": selected_consumer,
            "expected_consumer": spec.expected_consumer,
            "expected_next_action": spec.expected_next_action,
            "expected_required_artifact": spec.expected_required_artifact,
            "reviewer": spec.reviewer,
            "planned_step_id": str(planned_step.get("step_id") or ""),
            "planned_next_stage": str(planned_step.get("next_stage") or plan.get("source_chain_next_stage") or ""),
            "planned_next_action": next_action,
            "planned_required_artifact": required_artifact,
            "dispatch_target": dict(dispatch_target),
            "dispatcher_input": dispatcher_input,
            "dispatcher_input_ready_for_review": bool(dispatcher_input) and not blockers,
            "will_invoke_dispatch_target": False,
            "will_invoke_next_action": False,
            "will_record_approval": False,
            "will_run_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-preflight.v1",
            "status": status,
            "review_only": True,
            "preflight_only": True,
            "plan_only": True,
            "dispatch_preflight_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_one_step_plan_schema_version": "",
            "source_one_step_plan_status": "",
            "source_one_step_plan_digest_sha256": "",
            "selected_consumer": "",
            "expected_consumer": "",
            "expected_next_action": "",
            "expected_required_artifact": "",
            "reviewer": "",
            "planned_step_id": "",
            "planned_next_stage": "",
            "planned_next_action": "",
            "planned_required_artifact": "",
            "dispatch_target": {},
            "dispatcher_input": {},
            "dispatcher_input_ready_for_review": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_next_action": False,
            "will_record_approval": False,
            "will_run_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_one_step_plan_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _plan_blockers(cls, plan: dict[str, Any], planned_step: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not plan:
            return ["source_map_followthrough_one_step_plan_missing"]
        if plan.get("schema_version") not in {None, "", "reverse-deepagent.source-map-followthrough-one-step-plan.v1"}:
            blockers.append("source_map_followthrough_one_step_plan_schema_mismatch")
        if cls._status(plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_one_step_plan_not_ready")
        blockers.extend(f"source_map_followthrough_one_step_plan:{item}" for item in cls._string_list(plan.get("blockers")))
        if plan.get("planned_step_ready_for_review") is not True:
            blockers.append("source_map_followthrough_one_step_plan_not_ready_for_review")
        if not planned_step:
            blockers.append("source_map_followthrough_one_step_planned_step_missing")
        elif planned_step.get("requires_explicit_review") is not True:
            blockers.append("source_map_followthrough_one_step_explicit_review_gate_missing")
        if bool(plan.get("will_invoke_next_action")) or bool(plan.get("will_invoke_dispatch_target")) or bool(plan.get("automatic_execution_supported")):
            blockers.append("source_map_followthrough_one_step_automatic_execution_claim_detected")
        if planned_step.get("execute_automatically") is True or planned_step.get("executor_invoked") is True:
            blockers.append("source_map_followthrough_one_step_execution_claim_detected")
        policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_followthrough_one_step_plan"))
        step_policy = planned_step.get("side_effect_policy") if isinstance(planned_step.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(step_policy, prefix="source_map_followthrough_planned_step"))
        return blockers

    @classmethod
    def _expectation_blockers(cls, spec: SourceMapFollowthroughDispatchPreflightSpec, selected_consumer: str, next_action: str, required_artifact: str) -> list[str]:
        blockers: list[str] = []
        expected_consumer = cls._normalize_consumer(spec.expected_consumer)
        if expected_consumer and selected_consumer and expected_consumer != selected_consumer:
            blockers.append("source_map_followthrough_dispatch_consumer_mismatch")
        if spec.expected_next_action and next_action and spec.expected_next_action != next_action:
            blockers.append("source_map_followthrough_dispatch_next_action_mismatch")
        if spec.expected_required_artifact and required_artifact and spec.expected_required_artifact != required_artifact:
            blockers.append("source_map_followthrough_dispatch_required_artifact_mismatch")
        return blockers

    @classmethod
    def _dispatch_blockers(cls, selected_consumer: str, next_action: str, required_artifact: str, dispatch_target: dict[str, str]) -> list[str]:
        blockers: list[str] = []
        if not next_action:
            blockers.append("source_map_followthrough_dispatch_next_action_missing")
        if not required_artifact:
            blockers.append("source_map_followthrough_dispatch_required_artifact_missing")
        if not dispatch_target:
            blockers.append("source_map_followthrough_dispatch_target_unsupported")
            return blockers
        target_consumer = dispatch_target.get("consumer", "")
        if selected_consumer and selected_consumer != target_consumer:
            blockers.append("source_map_followthrough_dispatch_target_consumer_mismatch")
        if required_artifact and required_artifact != dispatch_target.get("result_artifact"):
            blockers.append("source_map_followthrough_dispatch_target_artifact_mismatch")
        return blockers

    @classmethod
    def _dispatcher_input(cls, plan: dict[str, Any], planned_step: dict[str, Any], dispatch_target: dict[str, str], spec: SourceMapFollowthroughDispatchPreflightSpec) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-input.v1",
            "dispatch_surface": dispatch_target.get("dispatch_surface", ""),
            "selected_consumer": dispatch_target.get("consumer", ""),
            "next_action": planned_step.get("next_action") or plan.get("source_chain_next_action") or "",
            "required_result_artifact": dispatch_target.get("result_artifact", ""),
            "review_gate": dispatch_target.get("review_gate", ""),
            "source_one_step_plan_digest_sha256": cls._stable_json_digest(plan),
            "planned_step_id": str(planned_step.get("step_id") or ""),
            "requires_explicit_review": True,
            "requires_separate_executor_call": True,
            "dispatcher_invoked": False,
            "executor_invoked": False,
            "approval_recorded": False,
            "apply_preflight_invoked": False,
            "reviewer": spec.reviewer,
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _warnings(plan: dict[str, Any], dispatcher_input: dict[str, Any]) -> list[str]:
        warnings = [
            "source_map_followthrough_dispatch_preflight_is_not_a_dispatcher",
            "separate_explicit_executor_call_required",
        ]
        if plan.get("warnings"):
            warnings.append("source_map_followthrough_one_step_plan_warnings_present")
        if dispatcher_input.get("required_result_artifact"):
            warnings.append("source_map_followthrough_result_artifact_required_after_dispatch")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if blockers:
            if any(item.startswith("source_map_followthrough_one_step_plan") for item in blockers):
                return "provide_ready_source_map_followthrough_one_step_plan_descriptor"
            return "resolve_source_map_followthrough_dispatch_preflight_blockers"
        return "review_source_map_followthrough_dispatch_preflight_before_explicit_executor_call"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        normalized = value.strip().replace("_", "-").lower()
        aliases = {"source-logpoints": "source-logpoint", "logpoint": "source-logpoint", "logpoints": "source-logpoint", "rebuild-metadata": "rebuild"}
        return aliases.get(normalized, normalized)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "plan_only": True,
            "dispatch_preflight_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "apply_preflight_invoked": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughDispatchApprovalPlanSpec:
    """Review-only approval / transaction plan before dispatch execution."""

    source_map_followthrough_dispatch_preflight: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_dispatch_surface: str = ""
    expected_required_artifact: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughDispatchApprovalPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_dispatch_approval_plan",
                "sourceMapFollowthroughDispatchApprovalPlan",
                "source_map_followthrough_executor_approval_plan",
                "sourceMapFollowthroughExecutorApprovalPlan",
                "source_map_followthrough_dispatch_transaction_plan",
                "sourceMapFollowthroughDispatchTransactionPlan",
            )
        )
        preflight = cls._object_alias(
            context,
            "source_map_followthrough_dispatch_preflight",
            "source-map-followthrough-dispatch-preflight",
            "sourceMapFollowthroughDispatchPreflight",
            "source_map_followthrough_dispatch_review",
            "source-map-followthrough-dispatch-review",
            "sourceMapFollowthroughDispatchReview",
            "source_map_followthrough_executor_dispatch_preflight",
            "source-map-followthrough-executor-dispatch-preflight",
            "sourceMapFollowthroughExecutorDispatchPreflight",
        )
        if not requested and not preflight:
            return None
        return cls(
            source_map_followthrough_dispatch_preflight=preflight,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", "")) or ""),
            expected_dispatch_surface=str(context.get("expected_dispatch_surface", context.get("expectedDispatchSurface", "")) or ""),
            expected_required_artifact=str(context.get("expected_required_artifact", context.get("expectedRequiredArtifact", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughDispatchApprovalPlanResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "descriptor": self.descriptor, "side_effect_policy": self.side_effect_policy, "reason": self.reason, "error": self.error}


class SourceMapFollowthroughDispatchApprovalPlanManager:
    """Plan approval and transaction gates for one Source Map dispatch."""

    def review(self, spec: SourceMapFollowthroughDispatchApprovalPlanSpec | None) -> SourceMapFollowthroughDispatchApprovalPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughDispatchApprovalPlanResult(status="unsupported", reason="missing_source_map_followthrough_dispatch_approval_plan_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughDispatchApprovalPlanResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_dispatch_approval_plan_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughDispatchApprovalPlanResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_dispatch_approval_plan_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughDispatchApprovalPlanSpec) -> dict[str, Any]:
        preflight = spec.source_map_followthrough_dispatch_preflight
        dispatcher_input = preflight.get("dispatcher_input") if isinstance(preflight.get("dispatcher_input"), dict) else {}
        dispatch_target = preflight.get("dispatch_target") if isinstance(preflight.get("dispatch_target"), dict) else {}
        selected_consumer = self._normalize_consumer(str(preflight.get("selected_consumer") or dispatcher_input.get("selected_consumer") or spec.expected_consumer or ""))
        dispatch_surface = str(dispatch_target.get("dispatch_surface") or dispatcher_input.get("dispatch_surface") or spec.expected_dispatch_surface or "")
        required_artifact = str(preflight.get("planned_required_artifact") or dispatcher_input.get("required_result_artifact") or spec.expected_required_artifact or "")
        blockers = self._preflight_blockers(preflight, dispatcher_input)
        blockers.extend(self._expectation_blockers(spec, selected_consumer, dispatch_surface, required_artifact))
        approval_plan = {} if blockers else self._approval_plan(preflight, dispatcher_input, dispatch_surface, required_artifact, spec)
        transaction_plan = {} if blockers else self._transaction_plan(approval_plan, spec)
        warnings = self._warnings(preflight, approval_plan, transaction_plan)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-approval-plan.v1",
            "status": status,
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "plan_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "source_dispatch_preflight_schema_version": str(preflight.get("schema_version") or ""),
            "source_dispatch_preflight_status": self._status(preflight),
            "source_dispatch_preflight_digest_sha256": self._stable_json_digest(preflight) if preflight else "",
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "planned_required_artifact": required_artifact,
            "expected_consumer": spec.expected_consumer,
            "expected_dispatch_surface": spec.expected_dispatch_surface,
            "expected_required_artifact": spec.expected_required_artifact,
            "reviewer": spec.reviewer,
            "approval_plan": approval_plan,
            "transaction_plan": transaction_plan,
            "approval_plan_ready_for_review": bool(approval_plan) and not blockers,
            "transaction_plan_ready_for_review": bool(transaction_plan) and not blockers,
            "ready_to_dispatch_now": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
            "will_write_approval_record": False,
            "will_start_transaction": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_next_action": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-approval-plan.v1",
            "status": status,
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "plan_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_dispatch_preflight_schema_version": "",
            "source_dispatch_preflight_status": "",
            "source_dispatch_preflight_digest_sha256": "",
            "selected_consumer": "",
            "dispatch_surface": "",
            "planned_required_artifact": "",
            "approval_plan": {},
            "transaction_plan": {},
            "approval_plan_ready_for_review": False,
            "transaction_plan_ready_for_review": False,
            "ready_to_dispatch_now": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
            "will_write_approval_record": False,
            "will_start_transaction": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_next_action": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_dispatch_preflight_descriptor",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _preflight_blockers(cls, preflight: dict[str, Any], dispatcher_input: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not preflight:
            return ["source_map_followthrough_dispatch_preflight_missing"]
        if preflight.get("schema_version") not in {None, "", "reverse-deepagent.source-map-followthrough-dispatch-preflight.v1"}:
            blockers.append("source_map_followthrough_dispatch_preflight_schema_mismatch")
        if cls._status(preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_preflight_not_ready")
        blockers.extend(f"source_map_followthrough_dispatch_preflight:{item}" for item in cls._string_list(preflight.get("blockers")))
        if preflight.get("dispatcher_input_ready_for_review") is not True:
            blockers.append("source_map_followthrough_dispatch_preflight_input_not_ready")
        if not dispatcher_input:
            blockers.append("source_map_followthrough_dispatch_input_missing")
        elif dispatcher_input.get("requires_explicit_review") is not True:
            blockers.append("source_map_followthrough_dispatch_explicit_review_gate_missing")
        for key in ("will_invoke_dispatch_target", "will_invoke_next_action", "automatic_dispatch_supported", "automatic_execution_supported"):
            if preflight.get(key) is True:
                blockers.append("source_map_followthrough_dispatch_preflight_execution_claim_detected")
                break
        for key in ("dispatcher_invoked", "executor_invoked", "approval_recorded", "apply_preflight_invoked"):
            if dispatcher_input.get(key) is True:
                blockers.append("source_map_followthrough_dispatch_input_execution_claim_detected")
                break
        policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_followthrough_dispatch_preflight"))
        input_policy = dispatcher_input.get("side_effect_policy") if isinstance(dispatcher_input.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(input_policy, prefix="source_map_followthrough_dispatch_input"))
        return blockers

    @classmethod
    def _expectation_blockers(cls, spec: SourceMapFollowthroughDispatchApprovalPlanSpec, selected_consumer: str, dispatch_surface: str, required_artifact: str) -> list[str]:
        blockers: list[str] = []
        expected_consumer = cls._normalize_consumer(spec.expected_consumer)
        if expected_consumer and selected_consumer and expected_consumer != selected_consumer:
            blockers.append("source_map_followthrough_dispatch_approval_consumer_mismatch")
        if spec.expected_dispatch_surface and dispatch_surface and spec.expected_dispatch_surface != dispatch_surface:
            blockers.append("source_map_followthrough_dispatch_approval_surface_mismatch")
        if spec.expected_required_artifact and required_artifact and spec.expected_required_artifact != required_artifact:
            blockers.append("source_map_followthrough_dispatch_approval_required_artifact_mismatch")
        return blockers

    @classmethod
    def _approval_plan(cls, preflight: dict[str, Any], dispatcher_input: dict[str, Any], dispatch_surface: str, required_artifact: str, spec: SourceMapFollowthroughDispatchApprovalPlanSpec) -> dict[str, Any]:
        seed = {"surface": dispatch_surface, "artifact": required_artifact, "preflight": cls._stable_json_digest(preflight)}
        approval_id = "source-map-dispatch-approval-plan:" + hashlib.sha256(json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-approval.v1",
            "approval_plan_id": approval_id,
            "selected_consumer": dispatcher_input.get("selected_consumer") or preflight.get("selected_consumer") or "",
            "dispatch_surface": dispatch_surface,
            "next_action": dispatcher_input.get("next_action") or preflight.get("planned_next_action") or "",
            "required_result_artifact": required_artifact,
            "review_gate": dispatcher_input.get("review_gate") or "explicit_source_map_followthrough_dispatch_review",
            "source_dispatch_preflight_digest_sha256": cls._stable_json_digest(preflight),
            "requires_explicit_review": True,
            "requires_approval_record": True,
            "requires_transaction_journal": True,
            "approval_recorded": False,
            "ready_to_dispatch_now": False,
            "reviewer": spec.reviewer,
            "side_effect_policy": cls._side_effect_policy(),
        }

    @classmethod
    def _transaction_plan(cls, approval_plan: dict[str, Any], spec: SourceMapFollowthroughDispatchApprovalPlanSpec) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-plan.v1",
            "transaction_plan_id": "source-map-dispatch-transaction-plan:" + str(approval_plan.get("approval_plan_id", "missing")),
            "approval_plan_id": approval_plan.get("approval_plan_id", ""),
            "transaction_started": False,
            "journal_written_now": False,
            "journal_required_before_dispatch": True,
            "rollback_checkpoint_required": True,
            "ready_to_dispatch_now": False,
            "reviewer": spec.reviewer,
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _warnings(preflight: dict[str, Any], approval_plan: dict[str, Any], transaction_plan: dict[str, Any]) -> list[str]:
        warnings = ["source_map_followthrough_dispatch_approval_plan_is_not_an_approval_record", "separate_approval_record_required_before_dispatch"]
        if preflight.get("warnings"):
            warnings.append("source_map_followthrough_dispatch_preflight_warnings_present")
        if approval_plan and transaction_plan:
            warnings.append("source_map_followthrough_dispatch_transaction_journal_required")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if blockers:
            if any(item.startswith("source_map_followthrough_dispatch_preflight") for item in blockers):
                return "provide_ready_source_map_followthrough_dispatch_preflight_descriptor"
            return "resolve_source_map_followthrough_dispatch_approval_plan_blockers"
        return "review_source_map_followthrough_dispatch_approval_plan_before_recording_approval"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        normalized = value.strip().replace("_", "-").lower()
        aliases = {"source-logpoints": "source-logpoint", "logpoint": "source-logpoint", "logpoints": "source-logpoint", "rebuild-metadata": "rebuild"}
        return aliases.get(normalized, normalized)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "plan_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "approval_artifact_written": False,
            "transaction_started": False,
            "journal_written": False,
            "apply_preflight_invoked": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughDispatchTransactionPreflightSpec:
    """Read-only transaction preflight after dispatch approval recording."""

    source_map_followthrough_dispatch_approval_plan: dict[str, Any] = field(default_factory=dict)
    source_map_followthrough_dispatch_approval_record: dict[str, Any] = field(default_factory=dict)
    expected_approval_plan_id: str = ""
    expected_approval_record_id: str = ""
    expected_consumer: str = ""
    expected_dispatch_surface: str = ""
    expected_required_artifact: str = ""
    expected_plan_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughDispatchTransactionPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_dispatch_transaction_preflight",
                "sourceMapFollowthroughDispatchTransactionPreflight",
                "source_map_followthrough_dispatch_journal_preflight",
                "sourceMapFollowthroughDispatchJournalPreflight",
                "source_map_followthrough_dispatch_transaction_gate",
                "sourceMapFollowthroughDispatchTransactionGate",
            )
        )
        approval_plan = cls._object_alias(
            context,
            "source_map_followthrough_dispatch_approval_plan",
            "source-map-followthrough-dispatch-approval-plan",
            "sourceMapFollowthroughDispatchApprovalPlan",
            "source_map_followthrough_executor_approval_plan",
            "source-map-followthrough-executor-approval-plan",
            "sourceMapFollowthroughExecutorApprovalPlan",
            "source_map_followthrough_dispatch_transaction_plan",
            "source-map-followthrough-dispatch-transaction-plan",
            "sourceMapFollowthroughDispatchTransactionPlan",
        )
        approval_record = cls._object_alias(
            context,
            "source_map_followthrough_dispatch_approval_record",
            "source-map-followthrough-dispatch-approval-record",
            "sourceMapFollowthroughDispatchApprovalRecord",
            "source_map_followthrough_executor_approval_record",
            "source-map-followthrough-executor-approval-record",
            "sourceMapFollowthroughExecutorApprovalRecord",
            "source_map_followthrough_dispatch_review_record",
            "source-map-followthrough-dispatch-review-record",
            "sourceMapFollowthroughDispatchReviewRecord",
        )
        if not requested and not approval_plan and not approval_record:
            return None
        return cls(
            source_map_followthrough_dispatch_approval_plan=approval_plan,
            source_map_followthrough_dispatch_approval_record=approval_record,
            expected_approval_plan_id=str(context.get("expected_approval_plan_id", context.get("expectedApprovalPlanId", "")) or ""),
            expected_approval_record_id=str(context.get("expected_approval_record_id", context.get("expectedApprovalRecordId", "")) or ""),
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", "")) or ""),
            expected_dispatch_surface=str(context.get("expected_dispatch_surface", context.get("expectedDispatchSurface", "")) or ""),
            expected_required_artifact=str(context.get("expected_required_artifact", context.get("expectedRequiredArtifact", "")) or ""),
            expected_plan_digest_sha256=str(context.get("expected_plan_digest_sha256", context.get("expectedPlanDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughDispatchTransactionPreflightResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "descriptor": self.descriptor, "side_effect_policy": self.side_effect_policy, "reason": self.reason, "error": self.error}


class SourceMapFollowthroughDispatchTransactionPreflightManager:
    """Verify dispatch approval evidence before any transaction journal writer."""

    def review(self, spec: SourceMapFollowthroughDispatchTransactionPreflightSpec | None) -> SourceMapFollowthroughDispatchTransactionPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughDispatchTransactionPreflightResult(status="unsupported", reason="missing_source_map_followthrough_dispatch_transaction_preflight_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughDispatchTransactionPreflightResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_dispatch_transaction_preflight_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughDispatchTransactionPreflightResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_dispatch_transaction_preflight_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughDispatchTransactionPreflightSpec) -> dict[str, Any]:
        approval_descriptor = spec.source_map_followthrough_dispatch_approval_plan
        approval_record = spec.source_map_followthrough_dispatch_approval_record
        approval_plan = approval_descriptor.get("approval_plan") if isinstance(approval_descriptor.get("approval_plan"), dict) else {}
        transaction_plan = approval_descriptor.get("transaction_plan") if isinstance(approval_descriptor.get("transaction_plan"), dict) else {}
        selected_consumer = self._normalize_consumer(str(approval_descriptor.get("selected_consumer") or approval_plan.get("selected_consumer") or approval_record.get("selected_consumer") or spec.expected_consumer or ""))
        dispatch_surface = str(approval_descriptor.get("dispatch_surface") or approval_plan.get("dispatch_surface") or approval_record.get("dispatch_surface") or spec.expected_dispatch_surface or "")
        required_artifact = str(approval_descriptor.get("planned_required_artifact") or approval_plan.get("required_result_artifact") or approval_record.get("required_result_artifact") or spec.expected_required_artifact or "")
        approval_plan_digest = self._stable_json_digest(approval_descriptor) if approval_descriptor else ""
        blockers = self._approval_plan_blockers(approval_descriptor, approval_plan, transaction_plan)
        blockers.extend(self._approval_record_blockers(approval_record))
        blockers.extend(self._match_blockers(spec, approval_descriptor, approval_plan, transaction_plan, approval_record, selected_consumer, dispatch_surface, required_artifact, approval_plan_digest))
        transaction_preflight = {} if blockers else self._transaction_preflight(approval_descriptor, approval_plan, transaction_plan, approval_record, selected_consumer, dispatch_surface, required_artifact, spec)
        journal_writer_gate = {} if blockers else self._journal_writer_gate(transaction_preflight, transaction_plan, approval_record)
        warnings = self._warnings(approval_descriptor, approval_record, transaction_preflight)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight.v1",
            "status": status,
            "review_only": True,
            "read_only": True,
            "preflight_only": True,
            "transaction_preflight_only": True,
            "journal_writer_gate_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "source_dispatch_approval_plan_schema_version": str(approval_descriptor.get("schema_version") or ""),
            "source_dispatch_approval_plan_status": self._status(approval_descriptor),
            "source_dispatch_approval_plan_digest_sha256": approval_plan_digest,
            "source_dispatch_approval_record_schema_version": str(approval_record.get("schema_version") or ""),
            "source_dispatch_approval_record_status": self._status(approval_record),
            "source_dispatch_approval_record_digest_sha256": self._stable_json_digest(approval_record) if approval_record else "",
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "planned_required_artifact": required_artifact,
            "approval_plan_id": str(approval_plan.get("approval_plan_id") or approval_record.get("approval_plan_id") or ""),
            "approval_record_id": str(approval_record.get("approval_record_id") or ""),
            "transaction_plan_id": str(transaction_plan.get("transaction_plan_id") or approval_record.get("transaction_plan_id") or ""),
            "expected_approval_plan_id": spec.expected_approval_plan_id,
            "expected_approval_record_id": spec.expected_approval_record_id,
            "expected_consumer": spec.expected_consumer,
            "expected_dispatch_surface": spec.expected_dispatch_surface,
            "expected_required_artifact": spec.expected_required_artifact,
            "expected_plan_digest_sha256": spec.expected_plan_digest_sha256,
            "reviewer": spec.reviewer,
            "approval_record_verified": bool(approval_record) and not blockers,
            "transaction_plan_verified": bool(transaction_plan) and not blockers,
            "transaction_preflight_ready_for_review": bool(transaction_preflight) and not blockers,
            "journal_writer_gate_ready_for_review": bool(journal_writer_gate) and not blockers,
            "ready_to_write_now": False,
            "ready_to_dispatch_now": False,
            "approval_recorded": bool(approval_record.get("approval_recorded")) if approval_record else False,
            "approved_for_dispatch": bool(approval_record.get("approved_for_dispatch")) if approval_record else False,
            "transaction_started": False,
            "journal_written": False,
            "will_write_transaction_journal": False,
            "will_start_transaction": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_next_action": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "transaction_preflight": transaction_preflight,
            "journal_writer_gate": journal_writer_gate,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight.v1",
            "status": status,
            "review_only": True,
            "read_only": True,
            "preflight_only": True,
            "transaction_preflight_only": True,
            "journal_writer_gate_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_dispatch_approval_plan_schema_version": "",
            "source_dispatch_approval_plan_status": "",
            "source_dispatch_approval_plan_digest_sha256": "",
            "source_dispatch_approval_record_schema_version": "",
            "source_dispatch_approval_record_status": "",
            "source_dispatch_approval_record_digest_sha256": "",
            "selected_consumer": "",
            "dispatch_surface": "",
            "planned_required_artifact": "",
            "approval_plan_id": "",
            "approval_record_id": "",
            "transaction_plan_id": "",
            "approval_record_verified": False,
            "transaction_plan_verified": False,
            "transaction_preflight_ready_for_review": False,
            "journal_writer_gate_ready_for_review": False,
            "ready_to_write_now": False,
            "ready_to_dispatch_now": False,
            "approval_recorded": False,
            "approved_for_dispatch": False,
            "transaction_started": False,
            "journal_written": False,
            "will_write_transaction_journal": False,
            "will_start_transaction": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_next_action": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "transaction_preflight": {},
            "journal_writer_gate": {},
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_dispatch_approval_plan_and_record",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _approval_plan_blockers(cls, descriptor: dict[str, Any], approval_plan: dict[str, Any], transaction_plan: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not descriptor:
            return ["source_map_followthrough_dispatch_approval_plan_missing"]
        if descriptor.get("schema_version") != "reverse-deepagent.source-map-followthrough-dispatch-approval-plan.v1":
            blockers.append("source_map_followthrough_dispatch_approval_plan_schema_mismatch")
        if cls._status(descriptor) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_approval_plan_not_ready")
        blockers.extend(f"source_map_followthrough_dispatch_approval_plan:{item}" for item in cls._string_list(descriptor.get("blockers")))
        if descriptor.get("approval_plan_ready_for_review") is not True or descriptor.get("transaction_plan_ready_for_review") is not True:
            blockers.append("source_map_followthrough_dispatch_approval_plan_not_ready_for_review")
        if not approval_plan:
            blockers.append("source_map_followthrough_nested_approval_plan_missing")
        elif approval_plan.get("schema_version") != "reverse-deepagent.source-map-followthrough-dispatch-approval.v1":
            blockers.append("source_map_followthrough_nested_approval_plan_schema_mismatch")
        if not transaction_plan:
            blockers.append("source_map_followthrough_transaction_plan_missing")
        elif transaction_plan.get("schema_version") != "reverse-deepagent.source-map-followthrough-dispatch-transaction-plan.v1":
            blockers.append("source_map_followthrough_transaction_plan_schema_mismatch")
        if descriptor.get("ready_to_dispatch_now") is True or approval_plan.get("ready_to_dispatch_now") is True or transaction_plan.get("ready_to_dispatch_now") is True:
            blockers.append("source_map_followthrough_dispatch_ready_now_claim_detected")
        if descriptor.get("transaction_started") is True or transaction_plan.get("transaction_started") is True:
            blockers.append("source_map_followthrough_transaction_already_started")
        if descriptor.get("journal_written") is True or transaction_plan.get("journal_written_now") is True:
            blockers.append("source_map_followthrough_transaction_journal_already_written")
        if descriptor.get("will_invoke_dispatch_target") is True or descriptor.get("will_invoke_next_action") is True:
            blockers.append("source_map_followthrough_dispatch_execution_claim_detected")
        policy = descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(policy, prefix="source_map_followthrough_dispatch_approval_plan"))
        tx_policy = transaction_plan.get("side_effect_policy") if isinstance(transaction_plan.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._side_effect_blockers(tx_policy, prefix="source_map_followthrough_transaction_plan"))
        return blockers

    @classmethod
    def _approval_record_blockers(cls, record: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not record:
            return ["source_map_followthrough_dispatch_approval_record_missing"]
        if record.get("schema_version") != "reverse-deepagent.source-map-followthrough-dispatch-approval-record.v1":
            blockers.append("source_map_followthrough_dispatch_approval_record_schema_mismatch")
        if cls._status(record) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_approval_record_not_ready")
        blockers.extend(f"source_map_followthrough_dispatch_approval_record:{item}" for item in cls._string_list(record.get("blockers")))
        if record.get("status") != "written" or record.get("approval_recorded") is not True:
            blockers.append("source_map_followthrough_dispatch_approval_record_not_written")
        if record.get("approved_for_dispatch") is not True or record.get("decision") != "approved":
            blockers.append("source_map_followthrough_dispatch_not_approved")
        gates = record.get("dispatch_input_gates") if isinstance(record.get("dispatch_input_gates"), dict) else {}
        if gates.get("requires_transaction_preflight_followup") is not True:
            blockers.append("source_map_followthrough_transaction_preflight_followup_not_required")
        if gates.get("requires_transaction_journal_before_dispatch") is not True:
            blockers.append("source_map_followthrough_transaction_journal_not_required")
        if gates.get("ready_to_dispatch_now") is True or gates.get("transaction_started") is True or gates.get("journal_written") is True or gates.get("dispatch_target_invoked") is True or gates.get("executor_invoked") is True:
            blockers.append("source_map_followthrough_dispatch_approval_record_execution_claim_detected")
        policy = record.get("side_effect_policy") if isinstance(record.get("side_effect_policy"), dict) else {}
        blockers.extend(cls._record_side_effect_blockers(policy, prefix="source_map_followthrough_dispatch_approval_record"))
        return blockers

    @classmethod
    def _match_blockers(cls, spec: SourceMapFollowthroughDispatchTransactionPreflightSpec, descriptor: dict[str, Any], approval_plan: dict[str, Any], transaction_plan: dict[str, Any], record: dict[str, Any], selected_consumer: str, dispatch_surface: str, required_artifact: str, plan_digest: str) -> list[str]:
        blockers: list[str] = []
        approval_plan_id = str(approval_plan.get("approval_plan_id") or "")
        record_plan_id = str(record.get("approval_plan_id") or "")
        record_tx_id = str(record.get("transaction_plan_id") or "")
        tx_id = str(transaction_plan.get("transaction_plan_id") or "")
        if approval_plan_id and record_plan_id and approval_plan_id != record_plan_id:
            blockers.append("source_map_followthrough_dispatch_approval_plan_id_mismatch")
        if tx_id and record_tx_id and tx_id != record_tx_id:
            blockers.append("source_map_followthrough_dispatch_transaction_plan_id_mismatch")
        if record.get("selected_consumer") and selected_consumer and cls._normalize_consumer(str(record.get("selected_consumer"))) != selected_consumer:
            blockers.append("source_map_followthrough_dispatch_consumer_mismatch")
        if record.get("dispatch_surface") and dispatch_surface and record.get("dispatch_surface") != dispatch_surface:
            blockers.append("source_map_followthrough_dispatch_surface_mismatch")
        if record.get("required_result_artifact") and required_artifact and record.get("required_result_artifact") != required_artifact:
            blockers.append("source_map_followthrough_dispatch_required_artifact_mismatch")
        if record.get("approval_plan_digest_sha256") and plan_digest and record.get("approval_plan_digest_sha256") != plan_digest:
            blockers.append("source_map_followthrough_dispatch_approval_plan_digest_mismatch")
        if spec.expected_approval_plan_id and approval_plan_id != spec.expected_approval_plan_id:
            blockers.append("source_map_followthrough_expected_approval_plan_id_mismatch")
        if spec.expected_approval_record_id and record.get("approval_record_id") != spec.expected_approval_record_id:
            blockers.append("source_map_followthrough_expected_approval_record_id_mismatch")
        expected_consumer = cls._normalize_consumer(spec.expected_consumer)
        if expected_consumer and selected_consumer != expected_consumer:
            blockers.append("source_map_followthrough_expected_consumer_mismatch")
        if spec.expected_dispatch_surface and dispatch_surface != spec.expected_dispatch_surface:
            blockers.append("source_map_followthrough_expected_dispatch_surface_mismatch")
        if spec.expected_required_artifact and required_artifact != spec.expected_required_artifact:
            blockers.append("source_map_followthrough_expected_required_artifact_mismatch")
        if spec.expected_plan_digest_sha256 and plan_digest != spec.expected_plan_digest_sha256:
            blockers.append("source_map_followthrough_expected_approval_plan_digest_mismatch")
        return blockers

    @classmethod
    def _transaction_preflight(cls, descriptor: dict[str, Any], approval_plan: dict[str, Any], transaction_plan: dict[str, Any], record: dict[str, Any], selected_consumer: str, dispatch_surface: str, required_artifact: str, spec: SourceMapFollowthroughDispatchTransactionPreflightSpec) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight-gate.v1",
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "approval_plan_id": approval_plan.get("approval_plan_id", ""),
            "approval_record_id": record.get("approval_record_id", ""),
            "transaction_plan_id": transaction_plan.get("transaction_plan_id", ""),
            "source_dispatch_approval_plan_digest_sha256": cls._stable_json_digest(descriptor),
            "source_dispatch_approval_record_digest_sha256": cls._stable_json_digest(record),
            "review_gate": approval_plan.get("review_gate", "explicit_source_map_followthrough_dispatch_review"),
            "requires_explicit_review": True,
            "requires_transaction_journal": True,
            "requires_journal_writer_review": True,
            "approval_record_verified": True,
            "ready_to_write_now": False,
            "transaction_started": False,
            "journal_written": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "reviewer": spec.reviewer,
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _journal_writer_gate(transaction_preflight: dict[str, Any], transaction_plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-journal-writer-gate.v1",
            "transaction_plan_id": transaction_preflight.get("transaction_plan_id", ""),
            "approval_record_id": transaction_preflight.get("approval_record_id", ""),
            "journal_artifact": "workspace/source-map-followthrough-dispatch-transaction-journal.json",
            "requires_approval_record": True,
            "requires_ready_transaction_preflight": True,
            "requires_explicit_journal_write_approval": True,
            "journal_required_before_dispatch": bool(transaction_plan.get("journal_required_before_dispatch")),
            "approval_recorded": bool(record.get("approval_recorded")),
            "approved_for_dispatch": bool(record.get("approved_for_dispatch")),
            "ready_to_write_now": False,
            "journal_written_now": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
        }

    @staticmethod
    def _warnings(descriptor: dict[str, Any], record: dict[str, Any], transaction_preflight: dict[str, Any]) -> list[str]:
        warnings = ["source_map_followthrough_dispatch_transaction_preflight_is_not_a_journal_writer", "separate_transaction_journal_writer_required_before_dispatch"]
        if descriptor.get("warnings"):
            warnings.append("source_map_followthrough_dispatch_approval_plan_warnings_present")
        if record.get("metadata"):
            warnings.append("source_map_followthrough_dispatch_approval_record_metadata_present")
        if transaction_preflight:
            warnings.append("source_map_followthrough_dispatch_journal_writer_gate_ready_for_review")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if blockers:
            if any("approval_plan" in item for item in blockers):
                return "provide_ready_source_map_followthrough_dispatch_approval_plan_descriptor"
            if any("approval_record" in item or "approved" in item for item in blockers):
                return "write_approved_source_map_followthrough_dispatch_approval_record"
            return "resolve_source_map_followthrough_dispatch_transaction_preflight_blockers"
        return "review_source_map_followthrough_dispatch_transaction_journal_writer"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        normalized = value.strip().replace("_", "-").lower()
        aliases = {"source-logpoints": "source-logpoint", "logpoint": "source-logpoint", "logpoints": "source-logpoint", "rebuild-metadata": "rebuild"}
        return aliases.get(normalized, normalized)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)
    _string_list = staticmethod(SourceMapTypedPayloadPreflightManager._string_list)
    _side_effect_blockers = staticmethod(SourceMapTypedPayloadPreflightManager._side_effect_blockers)

    @classmethod
    def _record_side_effect_blockers(cls, policy: dict[str, Any], *, prefix: str) -> list[str]:
        blockers = cls._side_effect_blockers(policy, prefix=prefix)
        allowed_write_keys = {"files_mutated", "artifacts_written", "writes_approval_record", "approval_recorded"}
        for key, value in policy.items():
            if key in allowed_write_keys:
                continue
            if key in {"approval_record_writer", "dry_run_is_read_only"}:
                continue
            if value is True:
                blockers.append(f"{prefix}_{key}_side_effect_detected")
        if policy.get("transaction_started") is True or policy.get("journal_written") is True:
            blockers.append(f"{prefix}_transaction_or_journal_side_effect_detected")
        if policy.get("dispatch_target_invoked") is True or policy.get("executor_invoked") is True:
            blockers.append(f"{prefix}_dispatch_or_executor_side_effect_detected")
        return blockers

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "transaction_preflight_only": True,
            "journal_writer_gate_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "writes_transaction_journal": False,
            "approval_recorded_by_manager": False,
            "transaction_started": False,
            "journal_written": False,
            "ready_to_write_now": False,
            "ready_to_dispatch_now": False,
            "apply_preflight_invoked": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapFollowthroughDispatchBoundedExecutorGateSpec:
    """Read-only bounded executor gate after dispatch transaction journaling."""

    source_map_followthrough_dispatch_transaction_journal: dict[str, Any] = field(default_factory=dict)
    expected_journal_id: str = ""
    expected_transaction_preflight_id: str = ""
    expected_approval_record_id: str = ""
    expected_transaction_plan_id: str = ""
    expected_approval_plan_id: str = ""
    expected_consumer: str = ""
    expected_dispatch_surface: str = ""
    expected_required_artifact: str = ""
    expected_journal_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughDispatchBoundedExecutorGateSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_dispatch_bounded_executor_gate",
                "sourceMapFollowthroughDispatchBoundedExecutorGate",
                "source_map_followthrough_dispatch_bounded_gate",
                "sourceMapFollowthroughDispatchBoundedGate",
                "source_map_followthrough_dispatch_executor_gate",
                "sourceMapFollowthroughDispatchExecutorGate",
            )
        )
        journal = cls._object_alias(
            context,
            "source_map_followthrough_dispatch_transaction_journal",
            "source-map-followthrough-dispatch-transaction-journal",
            "sourceMapFollowthroughDispatchTransactionJournal",
            "source_map_followthrough_dispatch_journal",
            "source-map-followthrough-dispatch-journal",
            "sourceMapFollowthroughDispatchJournal",
        )
        if not requested and not journal:
            return None
        return cls(
            source_map_followthrough_dispatch_transaction_journal=journal,
            expected_journal_id=str(context.get("expected_journal_id", context.get("expectedJournalId", "")) or ""),
            expected_transaction_preflight_id=str(context.get("expected_transaction_preflight_id", context.get("expectedTransactionPreflightId", "")) or ""),
            expected_approval_record_id=str(context.get("expected_approval_record_id", context.get("expectedApprovalRecordId", "")) or ""),
            expected_transaction_plan_id=str(context.get("expected_transaction_plan_id", context.get("expectedTransactionPlanId", "")) or ""),
            expected_approval_plan_id=str(context.get("expected_approval_plan_id", context.get("expectedApprovalPlanId", "")) or ""),
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", "")) or ""),
            expected_dispatch_surface=str(context.get("expected_dispatch_surface", context.get("expectedDispatchSurface", "")) or ""),
            expected_required_artifact=str(context.get("expected_required_artifact", context.get("expectedRequiredArtifact", "")) or ""),
            expected_journal_digest_sha256=str(context.get("expected_journal_digest_sha256", context.get("expectedJournalDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughDispatchBoundedExecutorGateResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "descriptor": self.descriptor, "side_effect_policy": self.side_effect_policy, "reason": self.reason, "error": self.error}


class SourceMapFollowthroughDispatchBoundedExecutorGateManager:
    """Review the final bounded gate before any Source Map follow-through dispatcher handoff."""

    def review(self, spec: SourceMapFollowthroughDispatchBoundedExecutorGateSpec | None) -> SourceMapFollowthroughDispatchBoundedExecutorGateResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughDispatchBoundedExecutorGateResult(status="unsupported", reason="missing_source_map_followthrough_dispatch_bounded_executor_gate_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughDispatchBoundedExecutorGateResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_dispatch_bounded_executor_gate_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughDispatchBoundedExecutorGateResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_dispatch_bounded_executor_gate_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughDispatchBoundedExecutorGateSpec) -> dict[str, Any]:
        journal = spec.source_map_followthrough_dispatch_transaction_journal
        journal_digest = self._stable_json_digest(journal) if journal else ""
        dispatch_gates = journal.get("dispatch_input_gates") if isinstance(journal.get("dispatch_input_gates"), dict) else {}
        journal_summary = journal.get("journal_summary") if isinstance(journal.get("journal_summary"), dict) else {}
        selected_consumer = self._normalize_consumer(str(journal.get("selected_consumer") or spec.expected_consumer or ""))
        dispatch_surface = str(journal.get("dispatch_surface") or spec.expected_dispatch_surface or "")
        required_artifact = str(journal.get("required_result_artifact") or spec.expected_required_artifact or "")
        checks = self._checks(
            spec=spec,
            journal=journal,
            dispatch_gates=dispatch_gates,
            journal_summary=journal_summary,
            journal_digest=journal_digest,
            selected_consumer=selected_consumer,
            dispatch_surface=dispatch_surface,
            required_artifact=required_artifact,
        )
        blockers = [check["name"] for check in checks if not check["passed"]]
        ready = not blockers
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-bounded-executor-gate.v1",
            "status": "ready_for_review" if ready else "blocked",
            "review_only": True,
            "read_only": True,
            "bounded_executor_gate_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "source_transaction_journal_schema_version": str(journal.get("schema_version") or ""),
            "source_transaction_journal_status": self._status(journal),
            "source_transaction_journal_digest_sha256": journal_digest,
            "expected_journal_digest_sha256": spec.expected_journal_digest_sha256,
            "journal_id": str(journal.get("journal_id") or ""),
            "transaction_preflight_id": str(journal.get("transaction_preflight_id") or ""),
            "approval_record_id": str(journal.get("approval_record_id") or ""),
            "approval_plan_id": str(journal.get("approval_plan_id") or ""),
            "transaction_plan_id": str(journal.get("transaction_plan_id") or ""),
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "reviewer": spec.reviewer,
            "transaction_journal_verified": ready,
            "bounded_executor_gate_ready_for_review": ready,
            "ready_for_dispatcher_handoff_review": ready,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "transaction_started": bool(journal.get("transaction_started")) if journal else False,
            "journal_written": bool(journal.get("journal_written")) if journal else False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_next_action": False,
            "will_run_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "dispatcher_handoff_required": True,
            "bounded_dispatch_input": self._bounded_dispatch_input(journal, dispatch_gates, selected_consumer, dispatch_surface, required_artifact, ready),
            "future_dispatcher_contract": self._future_dispatcher_contract(selected_consumer, dispatch_surface, required_artifact, ready),
            "source_journal_summary": self._journal_summary(journal, journal_summary, dispatch_gates),
            "checks": checks,
            "blockers": blockers,
            "warnings": self._warnings(journal, ready),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-bounded-executor-gate.v1",
            "status": status,
            "review_only": True,
            "read_only": True,
            "bounded_executor_gate_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_transaction_journal_schema_version": "",
            "source_transaction_journal_status": "",
            "source_transaction_journal_digest_sha256": "",
            "journal_id": "",
            "transaction_preflight_id": "",
            "approval_record_id": "",
            "approval_plan_id": "",
            "transaction_plan_id": "",
            "selected_consumer": "",
            "dispatch_surface": "",
            "required_result_artifact": "",
            "transaction_journal_verified": False,
            "bounded_executor_gate_ready_for_review": False,
            "ready_for_dispatcher_handoff_review": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "transaction_started": False,
            "journal_written": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_next_action": False,
            "will_run_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "dispatcher_handoff_required": True,
            "bounded_dispatch_input": {},
            "future_dispatcher_contract": {},
            "source_journal_summary": {},
            "checks": [],
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_written_source_map_followthrough_dispatch_transaction_journal",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _checks(
        cls,
        *,
        spec: SourceMapFollowthroughDispatchBoundedExecutorGateSpec,
        journal: dict[str, Any],
        dispatch_gates: dict[str, Any],
        journal_summary: dict[str, Any],
        journal_digest: str,
        selected_consumer: str,
        dispatch_surface: str,
        required_artifact: str,
    ) -> list[dict[str, Any]]:
        blockers = journal.get("blockers") if isinstance(journal.get("blockers"), list) else []
        policy = journal.get("side_effect_policy") if isinstance(journal.get("side_effect_policy"), dict) else {}
        return [
            {"name": "transaction_journal_available", "passed": bool(journal), "details": {"journal_id": journal.get("journal_id")}},
            {"name": "transaction_journal_schema_matches", "passed": journal.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatch-transaction-journal.v1", "details": {"schema_version": journal.get("schema_version")}},
            {"name": "transaction_journal_written", "passed": journal.get("status") == "written" and journal.get("journal_written") is True, "details": {"status": journal.get("status"), "journal_written": journal.get("journal_written")}},
            {"name": "transaction_started", "passed": journal.get("transaction_started") is True and journal_summary.get("transaction_started") is True, "details": {"transaction_started": journal.get("transaction_started"), "summary_transaction_started": journal_summary.get("transaction_started")}},
            {"name": "journal_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
            {"name": "bounded_gate_followup_required", "passed": dispatch_gates.get("requires_bounded_dispatch_gate") is True or journal_summary.get("requires_bounded_dispatch_gate_followup") is True, "details": {"gate_requires_bounded_dispatch_gate": dispatch_gates.get("requires_bounded_dispatch_gate"), "summary_requires_bounded_dispatch_gate_followup": journal_summary.get("requires_bounded_dispatch_gate_followup")}},
            {"name": "explicit_dispatch_review_required", "passed": dispatch_gates.get("requires_explicit_dispatch_review") is True, "details": {"requires_explicit_dispatch_review": dispatch_gates.get("requires_explicit_dispatch_review")}},
            {"name": "journal_not_ready_to_dispatch_now", "passed": journal.get("ready_to_dispatch_now") is not True and dispatch_gates.get("ready_to_dispatch_now") is not True, "details": {"journal_ready_to_dispatch_now": journal.get("ready_to_dispatch_now"), "gate_ready_to_dispatch_now": dispatch_gates.get("ready_to_dispatch_now")}},
            {"name": "dispatch_target_not_invoked", "passed": journal.get("dispatch_target_invoked") is not True and journal_summary.get("dispatch_target_invoked") is not True and dispatch_gates.get("dispatch_target_invoked") is not True, "details": {"journal_dispatch_target_invoked": journal.get("dispatch_target_invoked"), "summary_dispatch_target_invoked": journal_summary.get("dispatch_target_invoked"), "gate_dispatch_target_invoked": dispatch_gates.get("dispatch_target_invoked")}},
            {"name": "executor_not_invoked", "passed": journal.get("executor_invoked") is not True and journal_summary.get("executor_invoked") is not True and dispatch_gates.get("executor_invoked") is not True, "details": {"journal_executor_invoked": journal.get("executor_invoked"), "summary_executor_invoked": journal_summary.get("executor_invoked"), "gate_executor_invoked": dispatch_gates.get("executor_invoked")}},
            {"name": "selected_consumer_supported", "passed": selected_consumer in {"debugger", "source-logpoint", "rebuild", "hook"}, "details": {"selected_consumer": selected_consumer}},
            {"name": "dispatch_surface_present", "passed": bool(dispatch_surface), "details": {"dispatch_surface": dispatch_surface}},
            {"name": "required_result_artifact_present", "passed": bool(required_artifact), "details": {"required_result_artifact": required_artifact}},
            {"name": "expected_journal_id_matches", "passed": not spec.expected_journal_id or journal.get("journal_id") == spec.expected_journal_id, "details": {"expected_journal_id": spec.expected_journal_id, "journal_id": journal.get("journal_id")}},
            {"name": "expected_transaction_preflight_id_matches", "passed": not spec.expected_transaction_preflight_id or journal.get("transaction_preflight_id") == spec.expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": spec.expected_transaction_preflight_id, "transaction_preflight_id": journal.get("transaction_preflight_id")}},
            {"name": "expected_approval_record_id_matches", "passed": not spec.expected_approval_record_id or journal.get("approval_record_id") == spec.expected_approval_record_id, "details": {"expected_approval_record_id": spec.expected_approval_record_id, "approval_record_id": journal.get("approval_record_id")}},
            {"name": "expected_transaction_plan_id_matches", "passed": not spec.expected_transaction_plan_id or journal.get("transaction_plan_id") == spec.expected_transaction_plan_id, "details": {"expected_transaction_plan_id": spec.expected_transaction_plan_id, "transaction_plan_id": journal.get("transaction_plan_id")}},
            {"name": "expected_approval_plan_id_matches", "passed": not spec.expected_approval_plan_id or journal.get("approval_plan_id") == spec.expected_approval_plan_id, "details": {"expected_approval_plan_id": spec.expected_approval_plan_id, "approval_plan_id": journal.get("approval_plan_id")}},
            {"name": "expected_consumer_matches", "passed": not spec.expected_consumer or selected_consumer == cls._normalize_consumer(spec.expected_consumer), "details": {"expected_consumer": spec.expected_consumer, "selected_consumer": selected_consumer}},
            {"name": "expected_dispatch_surface_matches", "passed": not spec.expected_dispatch_surface or dispatch_surface == spec.expected_dispatch_surface, "details": {"expected_dispatch_surface": spec.expected_dispatch_surface, "dispatch_surface": dispatch_surface}},
            {"name": "expected_required_artifact_matches", "passed": not spec.expected_required_artifact or required_artifact == spec.expected_required_artifact, "details": {"expected_required_artifact": spec.expected_required_artifact, "required_result_artifact": required_artifact}},
            {"name": "expected_journal_digest_matches", "passed": not spec.expected_journal_digest_sha256 or journal_digest == spec.expected_journal_digest_sha256, "details": {"expected_journal_digest_sha256": spec.expected_journal_digest_sha256, "transaction_journal_digest_sha256": journal_digest}},
            {"name": "journal_no_runtime_side_effects", "passed": cls._journal_has_no_runtime_side_effects(policy), "details": policy},
        ]

    @classmethod
    def _bounded_dispatch_input(cls, journal: dict[str, Any], dispatch_gates: dict[str, Any], selected_consumer: str, dispatch_surface: str, required_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-bounded-input.v1",
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "journal_id": journal.get("journal_id"),
            "transaction_preflight_id": journal.get("transaction_preflight_id"),
            "approval_record_id": journal.get("approval_record_id"),
            "transaction_plan_id": journal.get("transaction_plan_id"),
            "ready_for_dispatcher_handoff_review": ready,
            "ready_to_dispatch_now": False,
            "requires_explicit_dispatcher_handoff_review": True,
            "requires_separate_executor_call": True,
            "requires_apply_preflight_before_selected_executor": True,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "automatic_dispatch_allowed": False,
            "automatic_followthrough_allowed": False,
            "automatic_execution_allowed": False,
            "source_dispatch_gates": {
                "approval_record_verified": bool(dispatch_gates.get("approval_record_verified")),
                "transaction_plan_verified": bool(dispatch_gates.get("transaction_plan_verified")),
                "transaction_started": bool(dispatch_gates.get("transaction_started")),
                "journal_written": bool(dispatch_gates.get("journal_written")),
                "requires_bounded_dispatch_gate": bool(dispatch_gates.get("requires_bounded_dispatch_gate")),
                "requires_explicit_dispatch_review": bool(dispatch_gates.get("requires_explicit_dispatch_review")),
            },
        }

    @staticmethod
    def _future_dispatcher_contract(selected_consumer: str, dispatch_surface: str, required_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-contract.v1",
            "dispatcher_name": "dispatch_source_map_followthrough_next_action",
            "implemented": False,
            "contract_ready_for_review": ready,
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "input_artifact": "workspace/source-map-followthrough-dispatch-bounded-executor-gate.json",
            "result_artifact": "workspace/source-map-followthrough-dispatcher-handoff.json",
            "requires_explicit_review": True,
            "requires_matching_bounded_gate": True,
            "must_not_skip_selected_executor_apply_preflight": True,
            "must_not_invoke_unreviewed_executor": True,
            "allowed_terminal_statuses": ["not_run", "planned", "ready_for_review", "blocked", "failed"],
        }

    @staticmethod
    def _journal_summary(journal: dict[str, Any], journal_summary: dict[str, Any], dispatch_gates: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": journal.get("schema_version"),
            "status": journal.get("status"),
            "journal_written": bool(journal.get("journal_written")),
            "transaction_started": bool(journal.get("transaction_started")),
            "entry_count": journal_summary.get("entry_count"),
            "planned_entry_count": journal_summary.get("planned_entry_count"),
            "requires_bounded_dispatch_gate_followup": bool(journal_summary.get("requires_bounded_dispatch_gate_followup")),
            "ready_to_dispatch_now": bool(dispatch_gates.get("ready_to_dispatch_now")),
            "dispatch_target_invoked": bool(dispatch_gates.get("dispatch_target_invoked")),
            "executor_invoked": bool(dispatch_gates.get("executor_invoked")),
        }

    @staticmethod
    def _warnings(journal: dict[str, Any], ready: bool) -> list[str]:
        warnings = ["source_map_followthrough_dispatch_bounded_gate_is_not_a_dispatcher", "separate_dispatcher_handoff_required_before_executor_call"]
        if journal.get("metadata"):
            warnings.append("source_map_followthrough_dispatch_transaction_journal_metadata_present")
        if ready:
            warnings.append("source_map_followthrough_dispatch_bounded_gate_ready_for_dispatcher_handoff")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if blockers:
            return "resolve_source_map_followthrough_dispatch_bounded_executor_gate_blockers"
        return "review_source_map_followthrough_dispatcher_handoff"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughDispatchTransactionPreflightManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapFollowthroughDispatchTransactionPreflightManager._stable_json_digest(payload)

    @staticmethod
    def _journal_has_no_runtime_side_effects(policy: dict[str, Any]) -> bool:
        forbidden = (
            "ready_to_dispatch_now",
            "dispatch_target_invoked",
            "executor_invoked",
            "debugger_execution_performed",
            "runtime_evaluated",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "apply_preflight_invoked",
            "fetch_source_map",
            "source_map_fetched",
            "browser_started",
            "cdp_command_sent",
            "calls_mcp",
            "mobile_runtime_used",
        )
        return not any(bool(policy.get(key)) for key in forbidden)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "bounded_executor_gate_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "writes_transaction_journal": False,
            "transaction_started": False,
            "journal_written": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "apply_preflight_invoked": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)


@dataclass(slots=True)
class SourceMapFollowthroughDispatcherHandoffSpec:
    """Read-only handoff descriptor after the Source Map dispatch bounded gate."""

    source_map_followthrough_dispatch_bounded_executor_gate: dict[str, Any] = field(default_factory=dict)
    expected_gate_digest_sha256: str = ""
    expected_journal_id: str = ""
    expected_transaction_preflight_id: str = ""
    expected_approval_record_id: str = ""
    expected_transaction_plan_id: str = ""
    expected_approval_plan_id: str = ""
    expected_consumer: str = ""
    expected_dispatch_surface: str = ""
    expected_required_artifact: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughDispatcherHandoffSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_dispatcher_handoff",
                "sourceMapFollowthroughDispatcherHandoff",
                "source_map_followthrough_dispatch_handoff",
                "sourceMapFollowthroughDispatchHandoff",
                "source_map_followthrough_next_action_handoff",
                "sourceMapFollowthroughNextActionHandoff",
            )
        )
        gate = cls._object_alias(
            context,
            "source_map_followthrough_dispatch_bounded_executor_gate",
            "source-map-followthrough-dispatch-bounded-executor-gate",
            "sourceMapFollowthroughDispatchBoundedExecutorGate",
            "source_map_followthrough_dispatch_bounded_gate",
            "source-map-followthrough-dispatch-bounded-gate",
            "sourceMapFollowthroughDispatchBoundedGate",
            "source_map_followthrough_dispatch_executor_gate",
            "source-map-followthrough-dispatch-executor-gate",
            "sourceMapFollowthroughDispatchExecutorGate",
        )
        if not requested and not gate:
            return None
        return cls(
            source_map_followthrough_dispatch_bounded_executor_gate=gate,
            expected_gate_digest_sha256=str(context.get("expected_gate_digest_sha256", context.get("expectedGateDigestSha256", "")) or ""),
            expected_journal_id=str(context.get("expected_journal_id", context.get("expectedJournalId", "")) or ""),
            expected_transaction_preflight_id=str(context.get("expected_transaction_preflight_id", context.get("expectedTransactionPreflightId", "")) or ""),
            expected_approval_record_id=str(context.get("expected_approval_record_id", context.get("expectedApprovalRecordId", "")) or ""),
            expected_transaction_plan_id=str(context.get("expected_transaction_plan_id", context.get("expectedTransactionPlanId", "")) or ""),
            expected_approval_plan_id=str(context.get("expected_approval_plan_id", context.get("expectedApprovalPlanId", "")) or ""),
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", "")) or ""),
            expected_dispatch_surface=str(context.get("expected_dispatch_surface", context.get("expectedDispatchSurface", "")) or ""),
            expected_required_artifact=str(context.get("expected_required_artifact", context.get("expectedRequiredArtifact", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughDispatcherHandoffResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "descriptor": self.descriptor, "side_effect_policy": self.side_effect_policy, "reason": self.reason, "error": self.error}


class SourceMapFollowthroughDispatcherHandoffManager:
    """Build the review-only handoff before any Source Map follow-through dispatcher can run."""

    def review(self, spec: SourceMapFollowthroughDispatcherHandoffSpec | None) -> SourceMapFollowthroughDispatcherHandoffResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughDispatcherHandoffResult(status="unsupported", reason="missing_source_map_followthrough_dispatcher_handoff_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughDispatcherHandoffResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_dispatcher_handoff_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughDispatcherHandoffResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_dispatcher_handoff_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughDispatcherHandoffSpec) -> dict[str, Any]:
        gate = spec.source_map_followthrough_dispatch_bounded_executor_gate
        gate_digest = self._stable_json_digest(gate) if gate else ""
        bounded_input = gate.get("bounded_dispatch_input") if isinstance(gate.get("bounded_dispatch_input"), dict) else {}
        future_contract = gate.get("future_dispatcher_contract") if isinstance(gate.get("future_dispatcher_contract"), dict) else {}
        selected_consumer = self._normalize_consumer(str(gate.get("selected_consumer") or bounded_input.get("selected_consumer") or spec.expected_consumer or ""))
        dispatch_surface = str(gate.get("dispatch_surface") or bounded_input.get("dispatch_surface") or spec.expected_dispatch_surface or "")
        required_artifact = str(gate.get("required_result_artifact") or bounded_input.get("required_result_artifact") or spec.expected_required_artifact or "")
        checks = self._checks(
            spec=spec,
            gate=gate,
            bounded_input=bounded_input,
            future_contract=future_contract,
            gate_digest=gate_digest,
            selected_consumer=selected_consumer,
            dispatch_surface=dispatch_surface,
            required_artifact=required_artifact,
        )
        blockers = [check["name"] for check in checks if not check["passed"]]
        ready = not blockers
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-handoff.v1",
            "status": "ready_for_review" if ready else "blocked",
            "review_only": True,
            "read_only": True,
            "dispatcher_handoff_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "source_bounded_gate_schema_version": str(gate.get("schema_version") or ""),
            "source_bounded_gate_status": self._status(gate),
            "source_bounded_gate_digest_sha256": gate_digest,
            "expected_gate_digest_sha256": spec.expected_gate_digest_sha256,
            "journal_id": str(gate.get("journal_id") or bounded_input.get("journal_id") or ""),
            "transaction_preflight_id": str(gate.get("transaction_preflight_id") or bounded_input.get("transaction_preflight_id") or ""),
            "approval_record_id": str(gate.get("approval_record_id") or bounded_input.get("approval_record_id") or ""),
            "approval_plan_id": str(gate.get("approval_plan_id") or ""),
            "transaction_plan_id": str(gate.get("transaction_plan_id") or bounded_input.get("transaction_plan_id") or ""),
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "reviewer": spec.reviewer,
            "bounded_gate_verified": ready,
            "dispatcher_handoff_ready_for_review": ready,
            "ready_for_explicit_dispatch_review": ready,
            "ready_for_selected_executor_review": ready,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "apply_preflight_invoked": False,
            "will_invoke_dispatcher": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_selected_executor": False,
            "will_run_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "selected_executor_apply_preflight_required": True,
            "explicit_dispatcher_review_required": True,
            "dispatcher_handoff": self._dispatcher_handoff_payload(gate, bounded_input, future_contract, selected_consumer, dispatch_surface, required_artifact, ready),
            "selected_executor_review_contract": self._selected_executor_review_contract(selected_consumer, dispatch_surface, required_artifact, ready),
            "source_bounded_gate_summary": self._bounded_gate_summary(gate, bounded_input, future_contract),
            "checks": checks,
            "blockers": blockers,
            "warnings": self._warnings(gate, ready),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-handoff.v1",
            "status": status,
            "review_only": True,
            "read_only": True,
            "dispatcher_handoff_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_bounded_gate_schema_version": "",
            "source_bounded_gate_status": "",
            "source_bounded_gate_digest_sha256": "",
            "journal_id": "",
            "transaction_preflight_id": "",
            "approval_record_id": "",
            "approval_plan_id": "",
            "transaction_plan_id": "",
            "selected_consumer": "",
            "dispatch_surface": "",
            "required_result_artifact": "",
            "bounded_gate_verified": False,
            "dispatcher_handoff_ready_for_review": False,
            "ready_for_explicit_dispatch_review": False,
            "ready_for_selected_executor_review": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "apply_preflight_invoked": False,
            "will_invoke_dispatcher": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_selected_executor": False,
            "will_run_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "selected_executor_apply_preflight_required": True,
            "explicit_dispatcher_review_required": True,
            "dispatcher_handoff": {},
            "selected_executor_review_contract": {},
            "source_bounded_gate_summary": {},
            "checks": [],
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_dispatch_bounded_executor_gate",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _checks(
        cls,
        *,
        spec: SourceMapFollowthroughDispatcherHandoffSpec,
        gate: dict[str, Any],
        bounded_input: dict[str, Any],
        future_contract: dict[str, Any],
        gate_digest: str,
        selected_consumer: str,
        dispatch_surface: str,
        required_artifact: str,
    ) -> list[dict[str, Any]]:
        blockers = gate.get("blockers") if isinstance(gate.get("blockers"), list) else []
        policy = gate.get("side_effect_policy") if isinstance(gate.get("side_effect_policy"), dict) else {}
        return [
            {"name": "bounded_gate_available", "passed": bool(gate), "details": {"journal_id": gate.get("journal_id")}},
            {"name": "bounded_gate_schema_matches", "passed": gate.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatch-bounded-executor-gate.v1", "details": {"schema_version": gate.get("schema_version")}},
            {"name": "bounded_gate_ready", "passed": gate.get("status") == "ready_for_review" and gate.get("bounded_executor_gate_ready_for_review") is True, "details": {"status": gate.get("status"), "bounded_executor_gate_ready_for_review": gate.get("bounded_executor_gate_ready_for_review")}},
            {"name": "bounded_gate_ready_for_dispatcher_handoff", "passed": gate.get("ready_for_dispatcher_handoff_review") is True and bounded_input.get("ready_for_dispatcher_handoff_review") is True, "details": {"gate_ready_for_dispatcher_handoff_review": gate.get("ready_for_dispatcher_handoff_review"), "bounded_input_ready_for_dispatcher_handoff_review": bounded_input.get("ready_for_dispatcher_handoff_review")}},
            {"name": "transaction_journal_verified", "passed": gate.get("transaction_journal_verified") is True, "details": {"transaction_journal_verified": gate.get("transaction_journal_verified")}},
            {"name": "bounded_gate_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
            {"name": "selected_consumer_supported", "passed": selected_consumer in {"debugger", "source-logpoint", "rebuild", "hook"}, "details": {"selected_consumer": selected_consumer}},
            {"name": "dispatch_surface_present", "passed": bool(dispatch_surface), "details": {"dispatch_surface": dispatch_surface}},
            {"name": "required_result_artifact_present", "passed": bool(required_artifact), "details": {"required_result_artifact": required_artifact}},
            {"name": "future_dispatcher_contract_present", "passed": future_contract.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatcher-contract.v1", "details": {"schema_version": future_contract.get("schema_version")}},
            {"name": "future_dispatcher_contract_names_expected_dispatcher", "passed": future_contract.get("dispatcher_name") == "dispatch_source_map_followthrough_next_action", "details": {"dispatcher_name": future_contract.get("dispatcher_name")}},
            {"name": "future_dispatcher_contract_result_artifact_matches", "passed": future_contract.get("result_artifact") == "workspace/source-map-followthrough-dispatcher-handoff.json", "details": {"result_artifact": future_contract.get("result_artifact")}},
            {"name": "future_dispatcher_contract_requires_review", "passed": future_contract.get("requires_explicit_review") is True, "details": {"requires_explicit_review": future_contract.get("requires_explicit_review")}},
            {"name": "source_gate_not_ready_to_dispatch_now", "passed": gate.get("ready_to_dispatch_now") is not True and bounded_input.get("ready_to_dispatch_now") is not True, "details": {"gate_ready_to_dispatch_now": gate.get("ready_to_dispatch_now"), "bounded_input_ready_to_dispatch_now": bounded_input.get("ready_to_dispatch_now")}},
            {"name": "source_gate_not_ready_to_execute_now", "passed": gate.get("ready_to_execute_now") is not True, "details": {"gate_ready_to_execute_now": gate.get("ready_to_execute_now")}},
            {"name": "dispatch_target_not_invoked", "passed": gate.get("dispatch_target_invoked") is not True and bounded_input.get("dispatch_target_invoked") is not True, "details": {"gate_dispatch_target_invoked": gate.get("dispatch_target_invoked"), "bounded_input_dispatch_target_invoked": bounded_input.get("dispatch_target_invoked")}},
            {"name": "executor_not_invoked", "passed": gate.get("executor_invoked") is not True and bounded_input.get("executor_invoked") is not True, "details": {"gate_executor_invoked": gate.get("executor_invoked"), "bounded_input_executor_invoked": bounded_input.get("executor_invoked")}},
            {"name": "expected_gate_digest_matches", "passed": not spec.expected_gate_digest_sha256 or gate_digest == spec.expected_gate_digest_sha256, "details": {"expected_gate_digest_sha256": spec.expected_gate_digest_sha256, "source_bounded_gate_digest_sha256": gate_digest}},
            {"name": "expected_journal_id_matches", "passed": not spec.expected_journal_id or gate.get("journal_id") == spec.expected_journal_id, "details": {"expected_journal_id": spec.expected_journal_id, "journal_id": gate.get("journal_id")}},
            {"name": "expected_transaction_preflight_id_matches", "passed": not spec.expected_transaction_preflight_id or gate.get("transaction_preflight_id") == spec.expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": spec.expected_transaction_preflight_id, "transaction_preflight_id": gate.get("transaction_preflight_id")}},
            {"name": "expected_approval_record_id_matches", "passed": not spec.expected_approval_record_id or gate.get("approval_record_id") == spec.expected_approval_record_id, "details": {"expected_approval_record_id": spec.expected_approval_record_id, "approval_record_id": gate.get("approval_record_id")}},
            {"name": "expected_transaction_plan_id_matches", "passed": not spec.expected_transaction_plan_id or gate.get("transaction_plan_id") == spec.expected_transaction_plan_id, "details": {"expected_transaction_plan_id": spec.expected_transaction_plan_id, "transaction_plan_id": gate.get("transaction_plan_id")}},
            {"name": "expected_approval_plan_id_matches", "passed": not spec.expected_approval_plan_id or gate.get("approval_plan_id") == spec.expected_approval_plan_id, "details": {"expected_approval_plan_id": spec.expected_approval_plan_id, "approval_plan_id": gate.get("approval_plan_id")}},
            {"name": "expected_consumer_matches", "passed": not spec.expected_consumer or selected_consumer == cls._normalize_consumer(spec.expected_consumer), "details": {"expected_consumer": spec.expected_consumer, "selected_consumer": selected_consumer}},
            {"name": "expected_dispatch_surface_matches", "passed": not spec.expected_dispatch_surface or dispatch_surface == spec.expected_dispatch_surface, "details": {"expected_dispatch_surface": spec.expected_dispatch_surface, "dispatch_surface": dispatch_surface}},
            {"name": "expected_required_artifact_matches", "passed": not spec.expected_required_artifact or required_artifact == spec.expected_required_artifact, "details": {"expected_required_artifact": spec.expected_required_artifact, "required_result_artifact": required_artifact}},
            {"name": "bounded_gate_no_runtime_side_effects", "passed": cls._gate_has_no_runtime_side_effects(policy), "details": policy},
        ]

    @staticmethod
    def _dispatcher_handoff_payload(gate: dict[str, Any], bounded_input: dict[str, Any], future_contract: dict[str, Any], selected_consumer: str, dispatch_surface: str, required_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-handoff-input.v1",
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "source_bounded_gate_artifact": "workspace/source-map-followthrough-dispatch-bounded-executor-gate.json",
            "journal_id": gate.get("journal_id") or bounded_input.get("journal_id"),
            "transaction_preflight_id": gate.get("transaction_preflight_id") or bounded_input.get("transaction_preflight_id"),
            "approval_record_id": gate.get("approval_record_id") or bounded_input.get("approval_record_id"),
            "transaction_plan_id": gate.get("transaction_plan_id") or bounded_input.get("transaction_plan_id"),
            "dispatcher_name": future_contract.get("dispatcher_name") or "dispatch_source_map_followthrough_next_action",
            "ready_for_explicit_dispatch_review": ready,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "requires_explicit_dispatch_review": True,
            "requires_selected_executor_apply_preflight": True,
            "requires_separate_selected_executor_call": True,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "automatic_dispatch_allowed": False,
            "automatic_followthrough_allowed": False,
            "automatic_execution_allowed": False,
        }

    @staticmethod
    def _selected_executor_review_contract(selected_consumer: str, dispatch_surface: str, required_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-selected-executor-review-contract.v1",
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "ready_for_review": ready,
            "selected_executor_input_review_artifact": "workspace/source-map-selected-executor-input-review.json",
            "selected_executor_approval_plan_artifact": "workspace/source-map-selected-executor-approval-plan.json",
            "selected_executor_approval_record_artifact": "workspace/source-map-selected-executor-approval-record.json",
            "selected_executor_apply_preflight_artifact": "workspace/source-map-selected-executor-apply-preflight.json",
            "must_review_apply_preflight_before_executor": True,
            "must_not_invoke_executor_from_handoff": True,
        }

    @staticmethod
    def _bounded_gate_summary(gate: dict[str, Any], bounded_input: dict[str, Any], future_contract: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": gate.get("schema_version"),
            "status": gate.get("status"),
            "bounded_executor_gate_ready_for_review": bool(gate.get("bounded_executor_gate_ready_for_review")),
            "ready_for_dispatcher_handoff_review": bool(gate.get("ready_for_dispatcher_handoff_review")),
            "transaction_journal_verified": bool(gate.get("transaction_journal_verified")),
            "ready_to_dispatch_now": bool(gate.get("ready_to_dispatch_now")),
            "ready_to_execute_now": bool(gate.get("ready_to_execute_now")),
            "dispatch_target_invoked": bool(gate.get("dispatch_target_invoked")) or bool(bounded_input.get("dispatch_target_invoked")),
            "executor_invoked": bool(gate.get("executor_invoked")) or bool(bounded_input.get("executor_invoked")),
            "future_dispatcher_implemented": bool(future_contract.get("implemented")),
        }

    @staticmethod
    def _warnings(gate: dict[str, Any], ready: bool) -> list[str]:
        warnings = ["source_map_followthrough_dispatcher_handoff_is_not_a_dispatcher", "selected_executor_review_required_after_handoff"]
        if gate.get("future_dispatcher_contract"):
            warnings.append("source_map_followthrough_future_dispatcher_contract_consumed")
        if ready:
            warnings.append("source_map_followthrough_dispatcher_handoff_ready_for_explicit_dispatch_review")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if blockers:
            return "resolve_source_map_followthrough_dispatcher_handoff_blockers"
        return "review_source_map_followthrough_dispatcher_apply_preflight"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughDispatchTransactionPreflightManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapFollowthroughDispatchTransactionPreflightManager._stable_json_digest(payload)

    @staticmethod
    def _gate_has_no_runtime_side_effects(policy: dict[str, Any]) -> bool:
        forbidden = (
            "ready_to_dispatch_now",
            "ready_to_execute_now",
            "dispatch_target_invoked",
            "executor_invoked",
            "apply_preflight_invoked",
            "debugger_execution_performed",
            "runtime_evaluated",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "fetch_source_map",
            "source_map_fetched",
            "browser_started",
            "cdp_command_sent",
            "calls_mcp",
            "mobile_runtime_used",
        )
        return not any(bool(policy.get(key)) for key in forbidden)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "dispatcher_handoff_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "writes_transaction_journal": False,
            "transaction_started": False,
            "journal_written": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "apply_preflight_invoked": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)


@dataclass(slots=True)
class SourceMapFollowthroughDispatcherApplyPreflightSpec:
    """Read-only dispatcher apply-preflight descriptor after Source Map dispatcher handoff."""

    source_map_followthrough_dispatcher_handoff: dict[str, Any] = field(default_factory=dict)
    expected_handoff_digest_sha256: str = ""
    expected_journal_id: str = ""
    expected_transaction_preflight_id: str = ""
    expected_approval_record_id: str = ""
    expected_transaction_plan_id: str = ""
    expected_approval_plan_id: str = ""
    expected_consumer: str = ""
    expected_dispatch_surface: str = ""
    expected_required_artifact: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughDispatcherApplyPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_dispatcher_apply_preflight",
                "sourceMapFollowthroughDispatcherApplyPreflight",
                "source_map_followthrough_dispatch_apply_preflight",
                "sourceMapFollowthroughDispatchApplyPreflight",
                "source_map_followthrough_dispatcher_preflight",
                "sourceMapFollowthroughDispatcherPreflight",
            )
        )
        handoff = cls._object_alias(
            context,
            "source_map_followthrough_dispatcher_handoff",
            "source-map-followthrough-dispatcher-handoff",
            "sourceMapFollowthroughDispatcherHandoff",
            "source_map_followthrough_dispatch_handoff",
            "source-map-followthrough-dispatch-handoff",
            "sourceMapFollowthroughDispatchHandoff",
            "source_map_followthrough_next_action_handoff",
            "source-map-followthrough-next-action-handoff",
            "sourceMapFollowthroughNextActionHandoff",
        )
        if not requested and not handoff:
            return None
        return cls(
            source_map_followthrough_dispatcher_handoff=handoff,
            expected_handoff_digest_sha256=str(context.get("expected_handoff_digest_sha256", context.get("expectedHandoffDigestSha256", "")) or ""),
            expected_journal_id=str(context.get("expected_journal_id", context.get("expectedJournalId", "")) or ""),
            expected_transaction_preflight_id=str(context.get("expected_transaction_preflight_id", context.get("expectedTransactionPreflightId", "")) or ""),
            expected_approval_record_id=str(context.get("expected_approval_record_id", context.get("expectedApprovalRecordId", "")) or ""),
            expected_transaction_plan_id=str(context.get("expected_transaction_plan_id", context.get("expectedTransactionPlanId", "")) or ""),
            expected_approval_plan_id=str(context.get("expected_approval_plan_id", context.get("expectedApprovalPlanId", "")) or ""),
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", "")) or ""),
            expected_dispatch_surface=str(context.get("expected_dispatch_surface", context.get("expectedDispatchSurface", "")) or ""),
            expected_required_artifact=str(context.get("expected_required_artifact", context.get("expectedRequiredArtifact", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughDispatcherApplyPreflightResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "descriptor": self.descriptor, "side_effect_policy": self.side_effect_policy, "reason": self.reason, "error": self.error}


class SourceMapFollowthroughDispatcherApplyPreflightManager:
    """Review dispatcher handoff inputs before any explicit Source Map dispatcher MVP can run."""

    def review(self, spec: SourceMapFollowthroughDispatcherApplyPreflightSpec | None) -> SourceMapFollowthroughDispatcherApplyPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughDispatcherApplyPreflightResult(status="unsupported", reason="missing_source_map_followthrough_dispatcher_apply_preflight_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughDispatcherApplyPreflightResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_dispatcher_apply_preflight_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughDispatcherApplyPreflightResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_followthrough_dispatcher_apply_preflight_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughDispatcherApplyPreflightSpec) -> dict[str, Any]:
        handoff = spec.source_map_followthrough_dispatcher_handoff
        handoff_digest = self._stable_json_digest(handoff) if handoff else ""
        handoff_payload = handoff.get("dispatcher_handoff") if isinstance(handoff.get("dispatcher_handoff"), dict) else {}
        executor_contract = handoff.get("selected_executor_review_contract") if isinstance(handoff.get("selected_executor_review_contract"), dict) else {}
        selected_consumer = self._normalize_consumer(str(handoff.get("selected_consumer") or handoff_payload.get("selected_consumer") or spec.expected_consumer or ""))
        dispatch_surface = str(handoff.get("dispatch_surface") or handoff_payload.get("dispatch_surface") or spec.expected_dispatch_surface or "")
        required_artifact = str(handoff.get("required_result_artifact") or handoff_payload.get("required_result_artifact") or spec.expected_required_artifact or "")
        checks = self._checks(
            spec=spec,
            handoff=handoff,
            handoff_payload=handoff_payload,
            executor_contract=executor_contract,
            handoff_digest=handoff_digest,
            selected_consumer=selected_consumer,
            dispatch_surface=dispatch_surface,
            required_artifact=required_artifact,
        )
        blockers = [check["name"] for check in checks if not check["passed"]]
        ready = not blockers
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight.v1",
            "status": "ready_for_review" if ready else "blocked",
            "review_only": True,
            "read_only": True,
            "preflight_only": True,
            "dispatcher_apply_preflight_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "source_handoff_schema_version": str(handoff.get("schema_version") or ""),
            "source_handoff_status": self._status(handoff),
            "source_handoff_digest_sha256": handoff_digest,
            "expected_handoff_digest_sha256": spec.expected_handoff_digest_sha256,
            "journal_id": str(handoff.get("journal_id") or handoff_payload.get("journal_id") or ""),
            "transaction_preflight_id": str(handoff.get("transaction_preflight_id") or handoff_payload.get("transaction_preflight_id") or ""),
            "approval_record_id": str(handoff.get("approval_record_id") or handoff_payload.get("approval_record_id") or ""),
            "approval_plan_id": str(handoff.get("approval_plan_id") or ""),
            "transaction_plan_id": str(handoff.get("transaction_plan_id") or handoff_payload.get("transaction_plan_id") or ""),
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "reviewer": spec.reviewer,
            "handoff_verified": ready,
            "dispatcher_apply_preflight_ready_for_review": ready,
            "ready_for_explicit_dispatcher_mvp_review": ready,
            "ready_for_selected_executor_apply_review": ready,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "runtime_apply_preflight_invoked": False,
            "will_invoke_dispatcher": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_selected_executor": False,
            "will_run_selected_executor_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "dispatcher_apply_preflight": self._dispatcher_apply_preflight(handoff, handoff_payload, executor_contract, selected_consumer, dispatch_surface, required_artifact, ready),
            "future_dispatcher_mvp_contract": self._future_dispatcher_mvp_contract(selected_consumer, dispatch_surface, required_artifact, ready),
            "source_handoff_summary": self._handoff_summary(handoff, handoff_payload, executor_contract),
            "checks": checks,
            "blockers": blockers,
            "warnings": self._warnings(handoff, ready),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight.v1",
            "status": status,
            "review_only": True,
            "read_only": True,
            "preflight_only": True,
            "dispatcher_apply_preflight_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "reason": reason,
            "source_handoff_schema_version": "",
            "source_handoff_status": "",
            "source_handoff_digest_sha256": "",
            "journal_id": "",
            "transaction_preflight_id": "",
            "approval_record_id": "",
            "approval_plan_id": "",
            "transaction_plan_id": "",
            "selected_consumer": "",
            "dispatch_surface": "",
            "required_result_artifact": "",
            "handoff_verified": False,
            "dispatcher_apply_preflight_ready_for_review": False,
            "ready_for_explicit_dispatcher_mvp_review": False,
            "ready_for_selected_executor_apply_review": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "runtime_apply_preflight_invoked": False,
            "will_invoke_dispatcher": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_selected_executor": False,
            "will_run_selected_executor_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "dispatcher_apply_preflight": {},
            "future_dispatcher_mvp_contract": {},
            "source_handoff_summary": {},
            "checks": [],
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_dispatcher_handoff",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _checks(
        cls,
        *,
        spec: SourceMapFollowthroughDispatcherApplyPreflightSpec,
        handoff: dict[str, Any],
        handoff_payload: dict[str, Any],
        executor_contract: dict[str, Any],
        handoff_digest: str,
        selected_consumer: str,
        dispatch_surface: str,
        required_artifact: str,
    ) -> list[dict[str, Any]]:
        blockers = handoff.get("blockers") if isinstance(handoff.get("blockers"), list) else []
        policy = handoff.get("side_effect_policy") if isinstance(handoff.get("side_effect_policy"), dict) else {}
        return [
            {"name": "dispatcher_handoff_available", "passed": bool(handoff), "details": {"journal_id": handoff.get("journal_id")}},
            {"name": "dispatcher_handoff_schema_matches", "passed": handoff.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatcher-handoff.v1", "details": {"schema_version": handoff.get("schema_version")}},
            {"name": "dispatcher_handoff_ready", "passed": handoff.get("status") == "ready_for_review" and handoff.get("dispatcher_handoff_ready_for_review") is True, "details": {"status": handoff.get("status"), "dispatcher_handoff_ready_for_review": handoff.get("dispatcher_handoff_ready_for_review")}},
            {"name": "explicit_dispatch_review_ready", "passed": handoff.get("ready_for_explicit_dispatch_review") is True and handoff_payload.get("ready_for_explicit_dispatch_review") is True, "details": {"handoff_ready_for_explicit_dispatch_review": handoff.get("ready_for_explicit_dispatch_review"), "payload_ready_for_explicit_dispatch_review": handoff_payload.get("ready_for_explicit_dispatch_review")}},
            {"name": "selected_executor_review_ready", "passed": handoff.get("ready_for_selected_executor_review") is True and executor_contract.get("ready_for_review") is True, "details": {"ready_for_selected_executor_review": handoff.get("ready_for_selected_executor_review"), "contract_ready_for_review": executor_contract.get("ready_for_review")}},
            {"name": "dispatcher_handoff_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
            {"name": "selected_consumer_supported", "passed": selected_consumer in {"debugger", "source-logpoint", "rebuild", "hook"}, "details": {"selected_consumer": selected_consumer}},
            {"name": "dispatch_surface_present", "passed": bool(dispatch_surface), "details": {"dispatch_surface": dispatch_surface}},
            {"name": "required_result_artifact_present", "passed": bool(required_artifact), "details": {"required_result_artifact": required_artifact}},
            {"name": "dispatcher_handoff_payload_schema_matches", "passed": handoff_payload.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatcher-handoff-input.v1", "details": {"schema_version": handoff_payload.get("schema_version")}},
            {"name": "dispatcher_name_matches", "passed": handoff_payload.get("dispatcher_name") == "dispatch_source_map_followthrough_next_action", "details": {"dispatcher_name": handoff_payload.get("dispatcher_name")}},
            {"name": "selected_executor_review_contract_schema_matches", "passed": executor_contract.get("schema_version") == "reverse-deepagent.source-map-followthrough-selected-executor-review-contract.v1", "details": {"schema_version": executor_contract.get("schema_version")}},
            {"name": "selected_executor_apply_preflight_required", "passed": executor_contract.get("must_review_apply_preflight_before_executor") is True and handoff_payload.get("requires_selected_executor_apply_preflight") is True, "details": {"contract_must_review_apply_preflight_before_executor": executor_contract.get("must_review_apply_preflight_before_executor"), "payload_requires_selected_executor_apply_preflight": handoff_payload.get("requires_selected_executor_apply_preflight")}},
            {"name": "source_handoff_not_ready_to_dispatch_now", "passed": handoff.get("ready_to_dispatch_now") is not True and handoff_payload.get("ready_to_dispatch_now") is not True, "details": {"handoff_ready_to_dispatch_now": handoff.get("ready_to_dispatch_now"), "payload_ready_to_dispatch_now": handoff_payload.get("ready_to_dispatch_now")}},
            {"name": "source_handoff_not_ready_to_execute_now", "passed": handoff.get("ready_to_execute_now") is not True and handoff_payload.get("ready_to_execute_now") is not True, "details": {"handoff_ready_to_execute_now": handoff.get("ready_to_execute_now"), "payload_ready_to_execute_now": handoff_payload.get("ready_to_execute_now")}},
            {"name": "dispatcher_not_invoked", "passed": handoff.get("dispatcher_invoked") is not True and handoff_payload.get("dispatcher_invoked") is not True, "details": {"handoff_dispatcher_invoked": handoff.get("dispatcher_invoked"), "payload_dispatcher_invoked": handoff_payload.get("dispatcher_invoked")}},
            {"name": "dispatch_target_not_invoked", "passed": handoff.get("dispatch_target_invoked") is not True and handoff_payload.get("dispatch_target_invoked") is not True, "details": {"handoff_dispatch_target_invoked": handoff.get("dispatch_target_invoked"), "payload_dispatch_target_invoked": handoff_payload.get("dispatch_target_invoked")}},
            {"name": "executor_not_invoked", "passed": handoff.get("executor_invoked") is not True and handoff_payload.get("executor_invoked") is not True, "details": {"handoff_executor_invoked": handoff.get("executor_invoked"), "payload_executor_invoked": handoff_payload.get("executor_invoked")}},
            {"name": "selected_executor_apply_preflight_not_invoked", "passed": handoff.get("apply_preflight_invoked") is not True and handoff.get("selected_executor_apply_preflight_invoked") is not True, "details": {"handoff_apply_preflight_invoked": handoff.get("apply_preflight_invoked"), "selected_executor_apply_preflight_invoked": handoff.get("selected_executor_apply_preflight_invoked")}},
            {"name": "expected_handoff_digest_matches", "passed": not spec.expected_handoff_digest_sha256 or handoff_digest == spec.expected_handoff_digest_sha256, "details": {"expected_handoff_digest_sha256": spec.expected_handoff_digest_sha256, "source_handoff_digest_sha256": handoff_digest}},
            {"name": "expected_journal_id_matches", "passed": not spec.expected_journal_id or handoff.get("journal_id") == spec.expected_journal_id, "details": {"expected_journal_id": spec.expected_journal_id, "journal_id": handoff.get("journal_id")}},
            {"name": "expected_transaction_preflight_id_matches", "passed": not spec.expected_transaction_preflight_id or handoff.get("transaction_preflight_id") == spec.expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": spec.expected_transaction_preflight_id, "transaction_preflight_id": handoff.get("transaction_preflight_id")}},
            {"name": "expected_approval_record_id_matches", "passed": not spec.expected_approval_record_id or handoff.get("approval_record_id") == spec.expected_approval_record_id, "details": {"expected_approval_record_id": spec.expected_approval_record_id, "approval_record_id": handoff.get("approval_record_id")}},
            {"name": "expected_transaction_plan_id_matches", "passed": not spec.expected_transaction_plan_id or handoff.get("transaction_plan_id") == spec.expected_transaction_plan_id, "details": {"expected_transaction_plan_id": spec.expected_transaction_plan_id, "transaction_plan_id": handoff.get("transaction_plan_id")}},
            {"name": "expected_approval_plan_id_matches", "passed": not spec.expected_approval_plan_id or handoff.get("approval_plan_id") == spec.expected_approval_plan_id, "details": {"expected_approval_plan_id": spec.expected_approval_plan_id, "approval_plan_id": handoff.get("approval_plan_id")}},
            {"name": "expected_consumer_matches", "passed": not spec.expected_consumer or selected_consumer == cls._normalize_consumer(spec.expected_consumer), "details": {"expected_consumer": spec.expected_consumer, "selected_consumer": selected_consumer}},
            {"name": "expected_dispatch_surface_matches", "passed": not spec.expected_dispatch_surface or dispatch_surface == spec.expected_dispatch_surface, "details": {"expected_dispatch_surface": spec.expected_dispatch_surface, "dispatch_surface": dispatch_surface}},
            {"name": "expected_required_artifact_matches", "passed": not spec.expected_required_artifact or required_artifact == spec.expected_required_artifact, "details": {"expected_required_artifact": spec.expected_required_artifact, "required_result_artifact": required_artifact}},
            {"name": "dispatcher_handoff_no_runtime_side_effects", "passed": cls._handoff_has_no_runtime_side_effects(policy), "details": policy},
        ]

    @staticmethod
    def _dispatcher_apply_preflight(handoff: dict[str, Any], handoff_payload: dict[str, Any], executor_contract: dict[str, Any], selected_consumer: str, dispatch_surface: str, required_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight-input.v1",
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "source_dispatcher_handoff_artifact": "workspace/source-map-followthrough-dispatcher-handoff.json",
            "journal_id": handoff.get("journal_id") or handoff_payload.get("journal_id"),
            "transaction_preflight_id": handoff.get("transaction_preflight_id") or handoff_payload.get("transaction_preflight_id"),
            "approval_record_id": handoff.get("approval_record_id") or handoff_payload.get("approval_record_id"),
            "transaction_plan_id": handoff.get("transaction_plan_id") or handoff_payload.get("transaction_plan_id"),
            "dispatcher_name": handoff_payload.get("dispatcher_name") or "dispatch_source_map_followthrough_next_action",
            "ready_for_explicit_dispatcher_mvp_review": ready,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "requires_explicit_dispatcher_mvp_review": True,
            "requires_selected_executor_apply_preflight": True,
            "selected_executor_apply_preflight_artifact": executor_contract.get("selected_executor_apply_preflight_artifact") or "workspace/source-map-selected-executor-apply-preflight.json",
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "automatic_dispatch_allowed": False,
            "automatic_followthrough_allowed": False,
            "automatic_execution_allowed": False,
        }

    @staticmethod
    def _future_dispatcher_mvp_contract(selected_consumer: str, dispatch_surface: str, required_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-mvp-contract.v1",
            "dispatcher_name": "dispatch_source_map_followthrough_next_action",
            "implemented": False,
            "contract_ready_for_review": ready,
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "input_artifact": "workspace/source-map-followthrough-dispatcher-apply-preflight.json",
            "result_artifact": "workspace/source-map-followthrough-dispatcher-result.json",
            "requires_explicit_review": True,
            "requires_matching_dispatcher_handoff": True,
            "requires_selected_executor_apply_preflight": True,
            "must_not_skip_selected_executor_apply_preflight": True,
            "must_not_invoke_unreviewed_executor": True,
            "allowed_terminal_statuses": ["not_run", "planned", "ready_for_review", "blocked", "failed"],
        }

    @staticmethod
    def _handoff_summary(handoff: dict[str, Any], handoff_payload: dict[str, Any], executor_contract: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": handoff.get("schema_version"),
            "status": handoff.get("status"),
            "dispatcher_handoff_ready_for_review": bool(handoff.get("dispatcher_handoff_ready_for_review")),
            "ready_for_explicit_dispatch_review": bool(handoff.get("ready_for_explicit_dispatch_review")),
            "ready_for_selected_executor_review": bool(handoff.get("ready_for_selected_executor_review")),
            "ready_to_dispatch_now": bool(handoff.get("ready_to_dispatch_now")) or bool(handoff_payload.get("ready_to_dispatch_now")),
            "ready_to_execute_now": bool(handoff.get("ready_to_execute_now")) or bool(handoff_payload.get("ready_to_execute_now")),
            "dispatcher_invoked": bool(handoff.get("dispatcher_invoked")) or bool(handoff_payload.get("dispatcher_invoked")),
            "dispatch_target_invoked": bool(handoff.get("dispatch_target_invoked")) or bool(handoff_payload.get("dispatch_target_invoked")),
            "executor_invoked": bool(handoff.get("executor_invoked")) or bool(handoff_payload.get("executor_invoked")),
            "selected_executor_apply_preflight_artifact": executor_contract.get("selected_executor_apply_preflight_artifact"),
        }

    @staticmethod
    def _warnings(handoff: dict[str, Any], ready: bool) -> list[str]:
        warnings = ["source_map_followthrough_dispatcher_apply_preflight_is_not_dispatcher_execution", "explicit_dispatcher_mvp_review_required_after_preflight"]
        if handoff.get("dispatcher_handoff"):
            warnings.append("source_map_followthrough_dispatcher_handoff_consumed")
        if ready:
            warnings.append("source_map_followthrough_dispatcher_apply_preflight_ready_for_dispatcher_mvp_review")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if blockers:
            return "resolve_source_map_followthrough_dispatcher_apply_preflight_blockers"
        return "review_source_map_followthrough_dispatcher_mvp"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughDispatchTransactionPreflightManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapFollowthroughDispatchTransactionPreflightManager._stable_json_digest(payload)

    @staticmethod
    def _handoff_has_no_runtime_side_effects(policy: dict[str, Any]) -> bool:
        forbidden = (
            "ready_to_dispatch_now",
            "ready_to_execute_now",
            "dispatcher_invoked",
            "dispatch_target_invoked",
            "executor_invoked",
            "selected_executor_invoked",
            "apply_preflight_invoked",
            "selected_executor_apply_preflight_invoked",
            "debugger_execution_performed",
            "runtime_evaluated",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "fetch_source_map",
            "source_map_fetched",
            "browser_started",
            "cdp_command_sent",
            "calls_mcp",
            "mobile_runtime_used",
        )
        return not any(bool(policy.get(key)) for key in forbidden)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "dispatcher_apply_preflight_only": True,
            "orchestration_only": True,
            "handoff_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "writes_transaction_journal": False,
            "transaction_started": False,
            "journal_written": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "runtime_apply_preflight_invoked": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)


@dataclass(slots=True)
class SourceMapFollowthroughDispatcherResultSpec:
    """Explicit-review-only Source Map dispatcher MVP decision descriptor."""

    source_map_followthrough_dispatcher_apply_preflight: dict[str, Any] = field(default_factory=dict)
    mode: str = "dry-run"
    write_result: bool = False
    review_approved: bool = False
    approve_dispatcher_mvp: bool = False
    reviewer: str = ""
    expected_apply_preflight_digest_sha256: str = ""
    expected_journal_id: str = ""
    expected_transaction_preflight_id: str = ""
    expected_approval_record_id: str = ""
    expected_transaction_plan_id: str = ""
    expected_approval_plan_id: str = ""
    expected_consumer: str = ""
    expected_dispatch_surface: str = ""
    expected_required_artifact: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapFollowthroughDispatcherResultSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_followthrough_dispatcher_result",
                "sourceMapFollowthroughDispatcherResult",
                "source_map_followthrough_dispatcher_mvp",
                "sourceMapFollowthroughDispatcherMvp",
                "source_map_followthrough_dispatch_next_action",
                "sourceMapFollowthroughDispatchNextAction",
            )
        )
        apply_preflight = cls._object_alias(
            context,
            "source_map_followthrough_dispatcher_apply_preflight",
            "source-map-followthrough-dispatcher-apply-preflight",
            "sourceMapFollowthroughDispatcherApplyPreflight",
            "source_map_followthrough_dispatch_apply_preflight",
            "source-map-followthrough-dispatch-apply-preflight",
            "sourceMapFollowthroughDispatchApplyPreflight",
            "source_map_followthrough_dispatcher_preflight",
            "source-map-followthrough-dispatcher-preflight",
            "sourceMapFollowthroughDispatcherPreflight",
        )
        if not requested and not apply_preflight:
            return None
        return cls(
            source_map_followthrough_dispatcher_apply_preflight=apply_preflight,
            mode=str(context.get("mode", context.get("dispatcher_mode", context.get("dispatcherMode", "dry-run"))) or "dry-run"),
            write_result=bool(context.get("write_result", context.get("writeResult", False))),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            approve_dispatcher_mvp=bool(context.get("approve_dispatcher_mvp", context.get("approveDispatcherMvp", False))),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
            expected_apply_preflight_digest_sha256=str(context.get("expected_apply_preflight_digest_sha256", context.get("expectedApplyPreflightDigestSha256", "")) or ""),
            expected_journal_id=str(context.get("expected_journal_id", context.get("expectedJournalId", "")) or ""),
            expected_transaction_preflight_id=str(context.get("expected_transaction_preflight_id", context.get("expectedTransactionPreflightId", "")) or ""),
            expected_approval_record_id=str(context.get("expected_approval_record_id", context.get("expectedApprovalRecordId", "")) or ""),
            expected_transaction_plan_id=str(context.get("expected_transaction_plan_id", context.get("expectedTransactionPlanId", "")) or ""),
            expected_approval_plan_id=str(context.get("expected_approval_plan_id", context.get("expectedApprovalPlanId", "")) or ""),
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", "")) or ""),
            expected_dispatch_surface=str(context.get("expected_dispatch_surface", context.get("expectedDispatchSurface", "")) or ""),
            expected_required_artifact=str(context.get("expected_required_artifact", context.get("expectedRequiredArtifact", "")) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapFollowthroughDispatcherResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "descriptor": self.descriptor, "side_effect_policy": self.side_effect_policy, "reason": self.reason, "error": self.error}


class SourceMapFollowthroughDispatcherManager:
    """Record an explicit reviewed Source Map dispatcher MVP decision without invoking the selected executor."""

    def dispatch(self, spec: SourceMapFollowthroughDispatcherResultSpec | None) -> SourceMapFollowthroughDispatcherResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapFollowthroughDispatcherResult(status="unsupported", reason="missing_source_map_followthrough_dispatcher_result_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapFollowthroughDispatcherResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=descriptor.get("side_effect_policy", policy))
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_followthrough_dispatcher_result_failed")
            descriptor["error"] = str(exc)
            return SourceMapFollowthroughDispatcherResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=descriptor.get("side_effect_policy", policy),
                reason="source_map_followthrough_dispatcher_result_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapFollowthroughDispatcherResultSpec) -> dict[str, Any]:
        apply_preflight = spec.source_map_followthrough_dispatcher_apply_preflight
        apply_preflight_digest = self._stable_json_digest(apply_preflight) if apply_preflight else ""
        dispatcher_input = apply_preflight.get("dispatcher_apply_preflight") if isinstance(apply_preflight.get("dispatcher_apply_preflight"), dict) else {}
        future_contract = apply_preflight.get("future_dispatcher_mvp_contract") if isinstance(apply_preflight.get("future_dispatcher_mvp_contract"), dict) else {}
        selected_consumer = self._normalize_consumer(str(apply_preflight.get("selected_consumer") or dispatcher_input.get("selected_consumer") or future_contract.get("selected_consumer") or spec.expected_consumer or ""))
        dispatch_surface = str(apply_preflight.get("dispatch_surface") or dispatcher_input.get("dispatch_surface") or future_contract.get("dispatch_surface") or spec.expected_dispatch_surface or "")
        required_artifact = str(apply_preflight.get("required_result_artifact") or dispatcher_input.get("required_result_artifact") or future_contract.get("required_result_artifact") or spec.expected_required_artifact or "")
        selected_executor_apply_preflight_artifact = str(dispatcher_input.get("selected_executor_apply_preflight_artifact") or "workspace/source-map-selected-executor-apply-preflight.json")
        source_checks = self._source_checks(
            spec=spec,
            apply_preflight=apply_preflight,
            dispatcher_input=dispatcher_input,
            future_contract=future_contract,
            apply_preflight_digest=apply_preflight_digest,
            selected_consumer=selected_consumer,
            dispatch_surface=dispatch_surface,
            required_artifact=required_artifact,
        )
        blockers = [check["name"] for check in source_checks if not check["passed"]]
        source_ready = not blockers
        approval_checks = self._approval_checks(spec)
        approval_blockers = [check["name"] for check in approval_checks if not check["passed"]]
        apply_requested = spec.mode.strip().lower() == "apply" or spec.write_result
        approved = source_ready and apply_requested and not approval_blockers
        if not source_ready:
            status = "blocked"
        elif not apply_requested:
            status = "ready_for_review"
        elif approval_blockers:
            status = "review_required"
        else:
            status = "dispatched"
        dispatcher_result_id = f"source-map-dispatcher-result:{apply_preflight.get('journal_id') or dispatcher_input.get('journal_id') or apply_preflight_digest or 'unbound'}"
        decision_recorded = status == "dispatched"
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-result.v1",
            "status": status,
            "dispatcher_result_id": dispatcher_result_id,
            "explicit_review_only": True,
            "dispatcher_mvp": True,
            "decision_record_only": True,
            "audit_only": True,
            "source_apply_preflight_schema_version": str(apply_preflight.get("schema_version") or ""),
            "source_apply_preflight_status": self._status(apply_preflight),
            "source_apply_preflight_digest_sha256": apply_preflight_digest,
            "expected_apply_preflight_digest_sha256": spec.expected_apply_preflight_digest_sha256,
            "journal_id": str(apply_preflight.get("journal_id") or dispatcher_input.get("journal_id") or ""),
            "transaction_preflight_id": str(apply_preflight.get("transaction_preflight_id") or dispatcher_input.get("transaction_preflight_id") or ""),
            "approval_record_id": str(apply_preflight.get("approval_record_id") or dispatcher_input.get("approval_record_id") or ""),
            "approval_plan_id": str(apply_preflight.get("approval_plan_id") or ""),
            "transaction_plan_id": str(apply_preflight.get("transaction_plan_id") or dispatcher_input.get("transaction_plan_id") or ""),
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "selected_executor_apply_preflight_artifact": selected_executor_apply_preflight_artifact,
            "mode": spec.mode,
            "write_result": spec.write_result,
            "reviewer": spec.reviewer,
            "review_approved": spec.review_approved,
            "approve_dispatcher_mvp": spec.approve_dispatcher_mvp,
            "apply_preflight_verified": source_ready,
            "dispatcher_decision_recorded": decision_recorded,
            "dispatcher_mvp_invoked": decision_recorded,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "runtime_apply_preflight_invoked": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "ready_to_execute_selected_executor_now": False,
            "requires_selected_executor_apply_preflight": True,
            "requires_separate_selected_executor_apply_preflight": True,
            "requires_separate_selected_executor_execution": True,
            "must_not_skip_selected_executor_apply_preflight": True,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "will_invoke_dispatch_target": False,
            "will_invoke_selected_executor": False,
            "will_run_selected_executor_apply_preflight": False,
            "will_execute_debugger": False,
            "will_install_source_logpoint": False,
            "will_install_hook": False,
            "will_run_rebuild": False,
            "dispatch_decision": self._dispatch_decision_payload(
                dispatcher_result_id=dispatcher_result_id,
                selected_consumer=selected_consumer,
                dispatch_surface=dispatch_surface,
                required_artifact=required_artifact,
                selected_executor_apply_preflight_artifact=selected_executor_apply_preflight_artifact,
                decision_recorded=decision_recorded,
            ),
            "source_apply_preflight_summary": self._apply_preflight_summary(apply_preflight, dispatcher_input, future_contract),
            "checks": source_checks + approval_checks,
            "blockers": blockers,
            "approval_blockers": approval_blockers if apply_requested else [],
            "warnings": self._warnings(status=status, decision_recorded=decision_recorded),
            "next_action": self._next_action(status=status, selected_consumer=selected_consumer),
            "side_effect_policy": self._side_effect_policy(decision_recorded=decision_recorded),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-result.v1",
            "status": status,
            "dispatcher_result_id": "",
            "explicit_review_only": True,
            "dispatcher_mvp": True,
            "decision_record_only": True,
            "audit_only": True,
            "reason": reason,
            "source_apply_preflight_schema_version": "",
            "source_apply_preflight_status": "",
            "source_apply_preflight_digest_sha256": "",
            "journal_id": "",
            "transaction_preflight_id": "",
            "approval_record_id": "",
            "approval_plan_id": "",
            "transaction_plan_id": "",
            "selected_consumer": "",
            "dispatch_surface": "",
            "required_result_artifact": "",
            "selected_executor_apply_preflight_artifact": "workspace/source-map-selected-executor-apply-preflight.json",
            "mode": "",
            "write_result": False,
            "reviewer": "",
            "review_approved": False,
            "approve_dispatcher_mvp": False,
            "apply_preflight_verified": False,
            "dispatcher_decision_recorded": False,
            "dispatcher_mvp_invoked": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "runtime_apply_preflight_invoked": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "ready_to_execute_selected_executor_now": False,
            "requires_selected_executor_apply_preflight": True,
            "requires_separate_selected_executor_apply_preflight": True,
            "requires_separate_selected_executor_execution": True,
            "must_not_skip_selected_executor_apply_preflight": True,
            "automatic_dispatch_supported": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "dispatch_decision": {},
            "source_apply_preflight_summary": {},
            "checks": [],
            "blockers": [reason],
            "approval_blockers": [],
            "warnings": [],
            "next_action": "provide_ready_source_map_followthrough_dispatcher_apply_preflight",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _source_checks(
        cls,
        *,
        spec: SourceMapFollowthroughDispatcherResultSpec,
        apply_preflight: dict[str, Any],
        dispatcher_input: dict[str, Any],
        future_contract: dict[str, Any],
        apply_preflight_digest: str,
        selected_consumer: str,
        dispatch_surface: str,
        required_artifact: str,
    ) -> list[dict[str, Any]]:
        blockers = apply_preflight.get("blockers") if isinstance(apply_preflight.get("blockers"), list) else []
        policy = apply_preflight.get("side_effect_policy") if isinstance(apply_preflight.get("side_effect_policy"), dict) else {}
        return [
            {"name": "dispatcher_apply_preflight_available", "passed": bool(apply_preflight), "details": {"journal_id": apply_preflight.get("journal_id")}},
            {"name": "dispatcher_apply_preflight_schema_matches", "passed": apply_preflight.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight.v1", "details": {"schema_version": apply_preflight.get("schema_version")}},
            {"name": "dispatcher_apply_preflight_ready", "passed": apply_preflight.get("status") == "ready_for_review" and apply_preflight.get("dispatcher_apply_preflight_ready_for_review") is True and apply_preflight.get("ready_for_explicit_dispatcher_mvp_review") is True, "details": {"status": apply_preflight.get("status"), "dispatcher_apply_preflight_ready_for_review": apply_preflight.get("dispatcher_apply_preflight_ready_for_review"), "ready_for_explicit_dispatcher_mvp_review": apply_preflight.get("ready_for_explicit_dispatcher_mvp_review")}},
            {"name": "dispatcher_apply_preflight_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
            {"name": "dispatcher_apply_preflight_input_schema_matches", "passed": dispatcher_input.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight-input.v1", "details": {"schema_version": dispatcher_input.get("schema_version")}},
            {"name": "future_dispatcher_mvp_contract_present", "passed": future_contract.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatcher-mvp-contract.v1", "details": {"schema_version": future_contract.get("schema_version")}},
            {"name": "future_dispatcher_mvp_not_previously_implemented", "passed": future_contract.get("implemented") is False, "details": {"implemented": future_contract.get("implemented")}},
            {"name": "future_dispatcher_mvp_result_artifact_matches", "passed": future_contract.get("result_artifact") == "workspace/source-map-followthrough-dispatcher-result.json", "details": {"result_artifact": future_contract.get("result_artifact")}},
            {"name": "selected_consumer_supported", "passed": selected_consumer in {"debugger", "source-logpoint", "rebuild", "hook"}, "details": {"selected_consumer": selected_consumer}},
            {"name": "dispatch_surface_present", "passed": bool(dispatch_surface), "details": {"dispatch_surface": dispatch_surface}},
            {"name": "required_result_artifact_present", "passed": bool(required_artifact), "details": {"required_result_artifact": required_artifact}},
            {"name": "selected_executor_apply_preflight_required", "passed": dispatcher_input.get("requires_selected_executor_apply_preflight") is True and future_contract.get("requires_selected_executor_apply_preflight") is True, "details": {"dispatcher_input_requires_apply_preflight": dispatcher_input.get("requires_selected_executor_apply_preflight"), "future_contract_requires_apply_preflight": future_contract.get("requires_selected_executor_apply_preflight")}},
            {"name": "source_apply_preflight_not_ready_to_dispatch_now", "passed": apply_preflight.get("ready_to_dispatch_now") is not True and dispatcher_input.get("ready_to_dispatch_now") is not True, "details": {"apply_preflight_ready_to_dispatch_now": apply_preflight.get("ready_to_dispatch_now"), "dispatcher_input_ready_to_dispatch_now": dispatcher_input.get("ready_to_dispatch_now")}},
            {"name": "source_apply_preflight_not_ready_to_execute_now", "passed": apply_preflight.get("ready_to_execute_now") is not True and dispatcher_input.get("ready_to_execute_now") is not True, "details": {"apply_preflight_ready_to_execute_now": apply_preflight.get("ready_to_execute_now"), "dispatcher_input_ready_to_execute_now": dispatcher_input.get("ready_to_execute_now")}},
            {"name": "source_dispatcher_not_invoked", "passed": apply_preflight.get("dispatcher_invoked") is not True and dispatcher_input.get("dispatcher_invoked") is not True, "details": {"apply_preflight_dispatcher_invoked": apply_preflight.get("dispatcher_invoked"), "dispatcher_input_dispatcher_invoked": dispatcher_input.get("dispatcher_invoked")}},
            {"name": "source_dispatch_target_not_invoked", "passed": apply_preflight.get("dispatch_target_invoked") is not True and dispatcher_input.get("dispatch_target_invoked") is not True, "details": {"apply_preflight_dispatch_target_invoked": apply_preflight.get("dispatch_target_invoked"), "dispatcher_input_dispatch_target_invoked": dispatcher_input.get("dispatch_target_invoked")}},
            {"name": "source_executor_not_invoked", "passed": apply_preflight.get("executor_invoked") is not True and dispatcher_input.get("executor_invoked") is not True, "details": {"apply_preflight_executor_invoked": apply_preflight.get("executor_invoked"), "dispatcher_input_executor_invoked": dispatcher_input.get("executor_invoked")}},
            {"name": "selected_executor_apply_preflight_not_invoked", "passed": apply_preflight.get("selected_executor_apply_preflight_invoked") is not True and dispatcher_input.get("selected_executor_apply_preflight_invoked") is not True, "details": {"apply_preflight_selected_executor_apply_preflight_invoked": apply_preflight.get("selected_executor_apply_preflight_invoked"), "dispatcher_input_selected_executor_apply_preflight_invoked": dispatcher_input.get("selected_executor_apply_preflight_invoked")}},
            {"name": "expected_apply_preflight_digest_matches", "passed": not spec.expected_apply_preflight_digest_sha256 or apply_preflight_digest == spec.expected_apply_preflight_digest_sha256, "details": {"expected_apply_preflight_digest_sha256": spec.expected_apply_preflight_digest_sha256, "source_apply_preflight_digest_sha256": apply_preflight_digest}},
            {"name": "expected_journal_id_matches", "passed": not spec.expected_journal_id or apply_preflight.get("journal_id") == spec.expected_journal_id, "details": {"expected_journal_id": spec.expected_journal_id, "journal_id": apply_preflight.get("journal_id")}},
            {"name": "expected_transaction_preflight_id_matches", "passed": not spec.expected_transaction_preflight_id or apply_preflight.get("transaction_preflight_id") == spec.expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": spec.expected_transaction_preflight_id, "transaction_preflight_id": apply_preflight.get("transaction_preflight_id")}},
            {"name": "expected_approval_record_id_matches", "passed": not spec.expected_approval_record_id or apply_preflight.get("approval_record_id") == spec.expected_approval_record_id, "details": {"expected_approval_record_id": spec.expected_approval_record_id, "approval_record_id": apply_preflight.get("approval_record_id")}},
            {"name": "expected_transaction_plan_id_matches", "passed": not spec.expected_transaction_plan_id or apply_preflight.get("transaction_plan_id") == spec.expected_transaction_plan_id, "details": {"expected_transaction_plan_id": spec.expected_transaction_plan_id, "transaction_plan_id": apply_preflight.get("transaction_plan_id")}},
            {"name": "expected_approval_plan_id_matches", "passed": not spec.expected_approval_plan_id or apply_preflight.get("approval_plan_id") == spec.expected_approval_plan_id, "details": {"expected_approval_plan_id": spec.expected_approval_plan_id, "approval_plan_id": apply_preflight.get("approval_plan_id")}},
            {"name": "expected_consumer_matches", "passed": not spec.expected_consumer or selected_consumer == cls._normalize_consumer(spec.expected_consumer), "details": {"expected_consumer": spec.expected_consumer, "selected_consumer": selected_consumer}},
            {"name": "expected_dispatch_surface_matches", "passed": not spec.expected_dispatch_surface or dispatch_surface == spec.expected_dispatch_surface, "details": {"expected_dispatch_surface": spec.expected_dispatch_surface, "dispatch_surface": dispatch_surface}},
            {"name": "expected_required_artifact_matches", "passed": not spec.expected_required_artifact or required_artifact == spec.expected_required_artifact, "details": {"expected_required_artifact": spec.expected_required_artifact, "required_result_artifact": required_artifact}},
            {"name": "dispatcher_apply_preflight_no_runtime_side_effects", "passed": cls._apply_preflight_has_no_runtime_side_effects(policy), "details": policy},
        ]

    @staticmethod
    def _approval_checks(spec: SourceMapFollowthroughDispatcherResultSpec) -> list[dict[str, Any]]:
        return [
            {"name": "mode_apply", "passed": spec.mode.strip().lower() == "apply", "details": {"mode": spec.mode}},
            {"name": "write_result_requested", "passed": spec.write_result is True, "details": {"write_result": spec.write_result}},
            {"name": "review_approved", "passed": spec.review_approved is True, "details": {"review_approved": spec.review_approved}},
            {"name": "approve_dispatcher_mvp", "passed": spec.approve_dispatcher_mvp is True, "details": {"approve_dispatcher_mvp": spec.approve_dispatcher_mvp}},
            {"name": "reviewer_present", "passed": bool(spec.reviewer.strip()), "details": {"reviewer": spec.reviewer}},
        ]

    @staticmethod
    def _dispatch_decision_payload(
        *,
        dispatcher_result_id: str,
        selected_consumer: str,
        dispatch_surface: str,
        required_artifact: str,
        selected_executor_apply_preflight_artifact: str,
        decision_recorded: bool,
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-decision.v1",
            "dispatcher_result_id": dispatcher_result_id,
            "dispatcher_name": "dispatch_source_map_followthrough_next_action",
            "selected_consumer": selected_consumer,
            "dispatch_surface": dispatch_surface,
            "required_result_artifact": required_artifact,
            "decision_recorded": decision_recorded,
            "selected_executor_apply_preflight_artifact": selected_executor_apply_preflight_artifact,
            "next_review_action": "review_source_map_selected_executor_apply_preflight",
            "dispatch_target_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "requires_separate_selected_executor_apply_preflight": True,
            "requires_separate_selected_executor_execution": True,
        }

    @staticmethod
    def _apply_preflight_summary(apply_preflight: dict[str, Any], dispatcher_input: dict[str, Any], future_contract: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": apply_preflight.get("schema_version"),
            "status": apply_preflight.get("status"),
            "dispatcher_apply_preflight_ready_for_review": bool(apply_preflight.get("dispatcher_apply_preflight_ready_for_review")),
            "ready_for_explicit_dispatcher_mvp_review": bool(apply_preflight.get("ready_for_explicit_dispatcher_mvp_review")),
            "selected_consumer": apply_preflight.get("selected_consumer") or dispatcher_input.get("selected_consumer"),
            "dispatch_surface": apply_preflight.get("dispatch_surface") or dispatcher_input.get("dispatch_surface"),
            "required_result_artifact": apply_preflight.get("required_result_artifact") or dispatcher_input.get("required_result_artifact"),
            "future_dispatcher_mvp_implemented": bool(future_contract.get("implemented")),
            "future_dispatcher_mvp_result_artifact": future_contract.get("result_artifact"),
            "selected_executor_apply_preflight_artifact": dispatcher_input.get("selected_executor_apply_preflight_artifact"),
        }

    @staticmethod
    def _warnings(*, status: str, decision_recorded: bool) -> list[str]:
        warnings = ["source_map_followthrough_dispatcher_result_does_not_execute_selected_executor", "selected_executor_apply_preflight_still_required"]
        if status == "ready_for_review":
            warnings.append("source_map_followthrough_dispatcher_result_requires_explicit_apply_review")
        if status == "review_required":
            warnings.append("source_map_followthrough_dispatcher_result_review_approval_required")
        if decision_recorded:
            warnings.append("source_map_followthrough_dispatcher_result_ready_for_selected_executor_apply_preflight")
        return warnings

    @staticmethod
    def _next_action(*, status: str, selected_consumer: str) -> str:
        if status == "blocked":
            return "resolve_source_map_followthrough_dispatcher_result_blockers"
        if status == "review_required":
            return "approve_source_map_followthrough_dispatcher_mvp"
        if status == "dispatched":
            return "review_source_map_selected_executor_apply_preflight"
        return "review_source_map_followthrough_dispatcher_mvp"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughDispatchTransactionPreflightManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapFollowthroughDispatchTransactionPreflightManager._stable_json_digest(payload)

    @staticmethod
    def _apply_preflight_has_no_runtime_side_effects(policy: dict[str, Any]) -> bool:
        forbidden = (
            "ready_to_dispatch_now",
            "ready_to_execute_now",
            "dispatcher_invoked",
            "dispatch_target_invoked",
            "executor_invoked",
            "selected_executor_invoked",
            "selected_executor_apply_preflight_invoked",
            "runtime_apply_preflight_invoked",
            "debugger_execution_performed",
            "runtime_evaluated",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "fetch_source_map",
            "source_map_fetched",
            "browser_started",
            "cdp_command_sent",
            "calls_mcp",
            "mobile_runtime_used",
        )
        return not any(bool(policy.get(key)) for key in forbidden)

    @staticmethod
    def _side_effect_policy(*, decision_recorded: bool = False) -> dict[str, Any]:
        return {
            "explicit_review_only": True,
            "dispatcher_mvp": True,
            "decision_record_only": True,
            "audit_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "dispatcher_decision_recorded": decision_recorded,
            "dispatcher_mvp_invoked": decision_recorded,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "runtime_apply_preflight_invoked": False,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "ready_to_execute_selected_executor_now": False,
            "fetch_source_map": False,
            "source_map_fetched": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    _status = staticmethod(SourceMapTypedPayloadPreflightManager._status)


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
