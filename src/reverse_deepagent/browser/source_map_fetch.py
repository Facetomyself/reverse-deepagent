from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

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
