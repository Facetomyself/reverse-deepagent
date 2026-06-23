from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from reverse_deepagent.delivery import (
    ExternalDeliveryPackage,
    ExternalDeliveryProviderCapabilities,
    ExternalDeliveryProviderRegistration,
    ExternalDeliveryResult,
)

S3_COMPATIBLE_EXTERNAL_DELIVERY_PROVIDER_ID = "s3-compatible"
S3_COMPATIBLE_EXTERNAL_DELIVERY_PROVIDER_ALIASES = ("s3", "s3-object", "minio")
_FACTORY_INVOCATION_COUNT = 0


@dataclass(frozen=True, slots=True)
class S3CompatibleHttpResponse:
    """Minimal secret-safe response shape returned by the HTTP seam."""

    status_code: int | None
    error: str | None = None
    body: bytes = b""


S3CompatibleHttpRequester = Callable[[str, bytes, dict[str, str], str, float], S3CompatibleHttpResponse]


@dataclass(frozen=True)
class S3CompatibleExternalDeliveryProvider:
    """S3-compatible object upload provider baseline.

    The provider intentionally avoids boto3 and SDK credentials. It can either
    build a path-style object URL from endpoint/bucket/object_name or use an
    explicitly reviewed presigned upload_url. Dry-run is fully side-effect free;
    apply mode performs one HTTP PUT only after package.mode=apply and explicit
    approve_s3_delivery=True.
    """

    endpoint_url: str | None = None
    bucket: str | None = None
    object_name: str | None = None
    upload_url: str | None = None
    allow_reviewed_presigned_url: bool = False
    content_type: str = "application/json"
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    approve_s3_delivery: bool = False
    http_requester: S3CompatibleHttpRequester | None = None
    provider_id: str = S3_COMPATIBLE_EXTERNAL_DELIVERY_PROVIDER_ID

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        package_payload = package.to_dict()
        package_digest = _json_payload_sha256(package_payload)
        target = _resolve_target_url(
            endpoint_url=self.endpoint_url,
            bucket=self.bucket,
            object_name=self.object_name,
            upload_url=self.upload_url,
        )
        redacted_target_url = _redact_url_for_metadata(target.url)
        target_query_present = _url_has_query(target.url)
        target_userinfo_present = _url_has_userinfo(target.url)
        inline_material_allowed = bool(target.presigned and self.allow_reviewed_presigned_url and not target_userinfo_present)
        inline_material_absent_or_reviewed = not (target_query_present or target_userinfo_present) or inline_material_allowed
        local_ready = not package.local_errors
        content_type_configured = bool(str(self.content_type or "").strip())
        target_configured = bool(target.url)
        target_scheme_supported = _http_scheme_supported(target.url)
        package_mode_apply = package.mode == "apply"
        explicit_apply_approval = bool(self.approve_s3_delivery)
        apply_allowed = bool(dry_run or (package_mode_apply and explicit_apply_approval))
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_errors": package.local_errors},
            },
            {
                "name": "s3_target_configured",
                "passed": target_configured,
                "details": {
                    "configured": target_configured,
                    "target_mode": target.mode,
                    "bucket_name_digest_sha256": _optional_digest(target.bucket_name),
                    "object_name": target.object_name or None,
                },
            },
            {
                "name": "s3_target_url_scheme_supported",
                "passed": target_scheme_supported,
                "details": {"supported_schemes": ["http", "https"], "target_url": redacted_target_url},
            },
            {
                "name": "s3_target_url_has_no_unreviewed_inline_material",
                "passed": inline_material_absent_or_reviewed,
                "details": {
                    "target_url": redacted_target_url,
                    "query_redacted": target_query_present,
                    "userinfo_redacted": target_userinfo_present,
                    "reviewed_presigned_mode": bool(target.presigned and self.allow_reviewed_presigned_url),
                },
            },
            {
                "name": "s3_content_type_configured",
                "passed": content_type_configured,
                "details": {"configured": content_type_configured},
            },
            {
                "name": "s3_apply_intent_reviewed",
                "passed": apply_allowed,
                "details": {
                    "required_for_apply": True,
                    "dry_run": dry_run,
                    "package_mode_apply": package_mode_apply,
                    "explicit_apply_approval": explicit_apply_approval,
                },
            },
        ]
        preflight_blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        request_body = _delivery_request_body(
            provider_id=self.provider_id,
            package=package,
            package_digest=package_digest,
            object_name=target.object_name,
            created_at=created_at,
        )
        request_body_digest = hashlib.sha256(request_body).hexdigest()
        response_status_code: int | None = None
        request_error: str | None = None
        request_attempted = False
        delivered = False
        if dry_run:
            status = "planned" if not preflight_blocking_reasons else "blocked"
            blocking_reasons = preflight_blocking_reasons
        elif preflight_blocking_reasons:
            status = "blocked"
            blocking_reasons = preflight_blocking_reasons
        else:
            request_attempted = True
            response = self._put_object(target.url, request_body)
            response_status_code = response.status_code
            request_error = response.error
            delivered = bool(response_status_code is not None and 200 <= response_status_code < 300)
            checks.append(
                {
                    "name": "s3_object_put_successful",
                    "passed": delivered,
                    "details": {
                        "status_code": response_status_code,
                        "request_error": request_error,
                        "target_url": redacted_target_url,
                        "response_body_recorded": False,
                        "response_headers_recorded": False,
                    },
                }
            )
            blocking_reasons = [check["name"] for check in checks if not check["passed"]]
            status = "delivered" if delivered else "blocked"
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status=status,
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=delivered,
            package_digest_sha256=package_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=(
                ["review_s3_compatible_external_delivery_result"]
                if delivered
                else ["approve_s3_delivery_before_apply"]
                if dry_run and not blocking_reasons
                else ["fix_s3_compatible_external_delivery_blockers"]
            ),
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "s3-compatible-external-delivery-provider-baseline",
                "automatic_delivery": False,
                "publishes_externally": delivered,
                "dry_run_side_effect_free": True,
                "network_attempted": request_attempted,
                "target_mode": target.mode,
                "target_url": redacted_target_url,
                "target_query_redacted": target_query_present,
                "target_userinfo_redacted": target_userinfo_present,
                "reviewed_presigned_mode": bool(target.presigned and self.allow_reviewed_presigned_url),
                "bucket_name_digest_sha256": _optional_digest(target.bucket_name),
                "bucket_name_recorded": False,
                "object_name": target.object_name or None,
                "request_method": "PUT",
                "request_body_digest_sha256": request_body_digest,
                "request_body_bytes": len(request_body),
                "request_status_code": response_status_code,
                "request_error": request_error,
                "request_headers_recorded": False,
                "response_body_recorded": False,
                "response_headers_recorded": False,
                "provider_config_values_recorded": False,
                "configured_header_count": len(self.headers),
                "content_type": str(self.content_type or ""),
                "timeout_seconds": float(self.timeout_seconds),
                "http_library": "urllib.request" if self.http_requester is None else "injected-http-requester",
                "limitations": [
                    "baseline_http_put_only",
                    "does_not_implement_sigv4_signing",
                    "does_not_manage_buckets_or_acl",
                    "does_not_record_request_or_response_payloads",
                    "apply_requires_package_mode_apply_and_explicit_review_approval",
                ],
            },
        )

    def _put_object(self, url: str, body: bytes) -> S3CompatibleHttpResponse:
        request_headers = {
            "Content-Type": str(self.content_type or "application/json"),
            "Accept": "application/json, */*;q=0.1",
            "User-Agent": "reverse-deepagent-s3-compatible-provider/0.1",
            **{str(name): str(value) for name, value in self.headers.items()},
        }
        requester = self.http_requester or _stdlib_http_requester
        return requester(url, body, request_headers, "PUT", float(self.timeout_seconds))


def s3_compatible_external_delivery_provider_capabilities() -> ExternalDeliveryProviderCapabilities:
    """Return side-effect-free, non-secret S3-compatible provider metadata."""

    return ExternalDeliveryProviderCapabilities(
        provider_id=S3_COMPATIBLE_EXTERNAL_DELIVERY_PROVIDER_ID,
        display_name="S3-compatible object external delivery",
        transport="s3-compatible-object-storage",
        supports_external_delivery=True,
        review_only=False,
        metadata={
            "side_effect_free": True,
            "dry_run_side_effect_free": True,
            "writes_external_delivery_result": True,
            "publishes_externally": True,
            "external_boundary": "s3-compatible-object-storage",
            "sends_http_put": True,
            "cloud_sdk_required": False,
            "stdlib_http_supported": True,
            "injectable_requester_supported": True,
            "records_request_headers": False,
            "records_request_body": False,
            "records_response_body": False,
            "records_response_headers": False,
            "blocks_inline_url_query_by_default": True,
            "blocks_inline_url_userinfo": True,
            "supports_reviewed_presigned_put": True,
            "apply_requires_package_mode_apply": True,
            "apply_requires_explicit_review_approval": True,
            "metadata_loading_invokes_factory": False,
        },
    )


def create_s3_compatible_external_delivery_provider(**kwargs: Any) -> S3CompatibleExternalDeliveryProvider:
    """Factory used by ExternalDeliveryProviderRegistry.

    Registry metadata listing must not call this function. It only captures
    explicit runtime config and does not read environment variables, files, or
    network resources.
    """

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    return S3CompatibleExternalDeliveryProvider(
        endpoint_url=kwargs.get("endpoint_url"),
        bucket=kwargs.get("bucket"),
        object_name=kwargs.get("object_name") or kwargs.get("object"),
        upload_url=kwargs.get("upload_url") or kwargs.get("presigned_url"),
        allow_reviewed_presigned_url=bool(kwargs.get("allow_reviewed_presigned_url", False)),
        content_type=kwargs.get("content_type", "application/json"),
        headers=kwargs.get("headers") if isinstance(kwargs.get("headers"), dict) else {},
        timeout_seconds=kwargs.get("timeout_seconds", 10.0),
        approve_s3_delivery=bool(kwargs.get("approve_s3_delivery", False)),
        http_requester=kwargs.get("http_requester"),
    )


def external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    """Return the S3-compatible registration without creating providers."""

    return ExternalDeliveryProviderRegistration(
        provider_id=S3_COMPATIBLE_EXTERNAL_DELIVERY_PROVIDER_ID,
        aliases=S3_COMPATIBLE_EXTERNAL_DELIVERY_PROVIDER_ALIASES,
        capabilities=s3_compatible_external_delivery_provider_capabilities(),
        factory=create_s3_compatible_external_delivery_provider,
    )


def factory_invocation_count() -> int:
    return _FACTORY_INVOCATION_COUNT


def _stdlib_http_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float) -> S3CompatibleHttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read(0)
            return S3CompatibleHttpResponse(status_code=int(response.status), error=None, body=b"")
    except urllib.error.HTTPError as exc:
        return S3CompatibleHttpResponse(status_code=int(exc.code), error="HTTPError", body=b"")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return S3CompatibleHttpResponse(status_code=None, error=exc.__class__.__name__, body=b"")


@dataclass(frozen=True, slots=True)
class _ResolvedS3Target:
    url: str
    mode: str
    bucket_name: str
    object_name: str
    presigned: bool


def _resolve_target_url(*, endpoint_url: str | None, bucket: str | None, object_name: str | None, upload_url: str | None) -> _ResolvedS3Target:
    normalized_upload = _normalize_url(upload_url)
    normalized_object = _safe_object_name(object_name)
    if normalized_upload:
        return _ResolvedS3Target(
            url=normalized_upload,
            mode="reviewed-presigned-put-url",
            bucket_name="",
            object_name=normalized_object,
            presigned=True,
        )
    normalized_endpoint = _normalize_url(endpoint_url)
    normalized_bucket = _safe_path_segment(bucket)
    if not (normalized_endpoint and normalized_bucket and normalized_object):
        return _ResolvedS3Target(url="", mode="path-style-endpoint", bucket_name=normalized_bucket, object_name=normalized_object, presigned=False)
    endpoint_parts = urllib.parse.urlsplit(normalized_endpoint)
    base_path = endpoint_parts.path.rstrip("/")
    object_path = "/".join(urllib.parse.quote(part, safe="") for part in normalized_object.split("/"))
    target_path = f"{base_path}/{urllib.parse.quote(normalized_bucket, safe='')}/{object_path}"
    target_url = urllib.parse.urlunsplit((endpoint_parts.scheme, endpoint_parts.netloc, target_path, "", ""))
    return _ResolvedS3Target(
        url=target_url,
        mode="path-style-endpoint",
        bucket_name=normalized_bucket,
        object_name=normalized_object,
        presigned=False,
    )


def _delivery_request_body(
    *,
    provider_id: str,
    package: ExternalDeliveryPackage,
    package_digest: str,
    object_name: str,
    created_at: str,
) -> bytes:
    payload = {
        "provider_id": provider_id,
        "transaction_id": package.transaction_id,
        "created_at": created_at,
        "object_name": object_name or None,
        "package_digest_sha256": package_digest,
        "package": package.to_dict(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_digest(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_url(value: str | None) -> str:
    return str(value or "").strip().rstrip("/")


def _safe_path_segment(value: str | None) -> str:
    segment = str(value or "").strip().strip("/")
    segment = re.sub(r"\s+", "", segment)
    return segment


def _safe_object_name(value: str | None) -> str:
    name = str(value or "").replace("\\", "/").strip().strip("/")
    while "//" in name:
        name = name.replace("//", "/")
    parts = [part for part in name.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts)


def _http_scheme_supported(value: str) -> bool:
    return urllib.parse.urlsplit(value).scheme in {"http", "https"}


def _url_has_query(value: str) -> bool:
    return bool(value and urllib.parse.urlsplit(value).query)


def _url_has_userinfo(value: str) -> bool:
    if not value:
        return False
    parts = urllib.parse.urlsplit(value)
    return bool(parts.username or parts.password)


def _redact_url_for_metadata(value: str) -> str | None:
    if not value:
        return None
    parts = urllib.parse.urlsplit(value)
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    path = "/<redacted-object-target>" if parts.path else ""
    redacted = urllib.parse.urlunsplit((parts.scheme, netloc, path, "", ""))
    return redacted or None
