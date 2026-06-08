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
class SourceMapSelectedExecutorInputReviewSpec:
    """Review-only package for one selected Source Map follow-through executor input.

    This consumes the Step 273 surface-selection descriptor and turns the chosen
    debugger / source-logpoint / rebuild / hook executor input into a stable
    downstream review package.  It does not invoke that executor.
    """

    source_map_followthrough_surface_selection: dict[str, Any] = field(default_factory=dict)
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
        if not requested and not selection and not selected_review and not executor_input:
            return None
        return cls(
            source_map_followthrough_surface_selection=selection,
            selected_review=selected_review,
            selected_executor_input=executor_input,
            expected_action_id=str(
                context.get(
                    "source_map_selected_action_id",
                    context.get("sourceMapSelectedActionId", context.get("expected_action_id", context.get("expectedActionId", ""))),
                )
                or ""
            ),
            expected_consumer=str(
                context.get(
                    "source_map_selected_consumer",
                    context.get("sourceMapSelectedConsumer", context.get("expected_consumer", context.get("expectedConsumer", ""))),
                )
                or ""
            ),
            expected_surface=str(
                context.get(
                    "source_map_selected_surface",
                    context.get("sourceMapSelectedSurface", context.get("expected_surface", context.get("expectedSurface", ""))),
                )
                or ""
            ),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
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
        selected_review = dict(spec.selected_review) if isinstance(spec.selected_review, dict) else {}
        executor_input = dict(spec.selected_executor_input) if isinstance(spec.selected_executor_input, dict) else {}
        blockers = self._input_blockers(selection, selected_review, executor_input)
        blockers.extend(self._expectation_blockers(spec, selected_review, selection))
        if selected_review:
            blockers.extend(self._selected_review_blockers(selected_review, executor_input))
        package = {} if blockers else self._executor_review_package(selection, selected_review, executor_input, spec)
        blockers.extend(self._package_blockers(package))
        warnings = self._warnings(selection, selected_review, package)
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
    def _warnings(cls, selection: dict[str, Any], selected_review: dict[str, Any], package: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        warnings.extend(f"source_map_followthrough_surface_selection:{item}" for item in cls._string_list(selection.get("warnings")))
        if selected_review:
            warnings.append("selected_source_map_executor_input_requires_explicit_review")
        if package:
            warnings.append("selected_executor_input_review_does_not_execute_surface")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], package: dict[str, Any], consumer: str) -> str:
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
