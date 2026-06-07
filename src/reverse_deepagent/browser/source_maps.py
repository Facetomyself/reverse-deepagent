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
