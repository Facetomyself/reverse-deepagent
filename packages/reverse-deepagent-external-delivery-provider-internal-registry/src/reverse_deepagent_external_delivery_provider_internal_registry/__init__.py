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

INTERNAL_REGISTRY_EXTERNAL_DELIVERY_PROVIDER_ID = "internal-registry"
INTERNAL_REGISTRY_EXTERNAL_DELIVERY_PROVIDER_ALIASES = ("artifact-registry", "internal-artifacts")
_FACTORY_INVOCATION_COUNT = 0
_ALLOWED_METHODS = {"POST", "PUT"}


@dataclass(frozen=True, slots=True)
class InternalRegistryHttpResponse:
    """Minimal secret-safe response shape returned by the HTTP seam."""

    status_code: int | None
    error: str | None = None
    body: bytes = b""


InternalRegistryHttpRequester = Callable[[str, bytes, dict[str, str], str, float], InternalRegistryHttpResponse]


@dataclass(frozen=True)
class InternalRegistryExternalDeliveryProvider:
    """Minimal HTTP publication provider for reviewed internal artifact registries.

    Registration is intentionally metadata-only. Constructing the provider does
    not open a client or read environment state. Dry-run builds the exact
    publication plan without network I/O; apply performs one HTTP request only
    after package.mode=apply and explicit approval.
    """

    registry_endpoint_url: str | None = None
    namespace: str | None = None
    project: str | None = None
    repository: str | None = None
    package_name: str | None = None
    package_version: str | None = None
    publication_contract: str = "reviewed-json-package"
    method: str = "POST"
    content_type: str = "application/json"
    headers: dict[str, str] = field(default_factory=dict)
    auth_token: str | None = None
    timeout_seconds: float = 10.0
    approve_internal_registry_delivery: bool = False
    http_requester: InternalRegistryHttpRequester | None = None
    provider_id: str = INTERNAL_REGISTRY_EXTERNAL_DELIVERY_PROVIDER_ID

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
        endpoint = _normalise_endpoint(self.registry_endpoint_url)
        redacted_endpoint = _redact_url_for_metadata(endpoint)
        endpoint_query_present = _url_has_query(endpoint)
        endpoint_userinfo_present = _url_has_userinfo(endpoint)
        endpoint_inline_secret_material_absent = not (endpoint_query_present or endpoint_userinfo_present)
        local_ready = not package.local_errors
        method = str(self.method or "POST").upper()
        method_supported = method in _ALLOWED_METHODS
        endpoint_configured = bool(endpoint)
        endpoint_scheme_supported = _http_scheme_supported(endpoint)
        content_type_configured = bool(str(self.content_type or "").strip())
        package_mode_apply = package.mode == "apply"
        explicit_apply_approval = bool(self.approve_internal_registry_delivery)
        apply_allowed = bool(dry_run or (package_mode_apply and explicit_apply_approval))
        identity = _identity_summary(namespace=self.namespace, project=self.project, repository=self.repository)
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_error_count": len(package.local_errors), "local_errors_recorded": False},
            },
            {
                "name": "internal_registry_endpoint_configured",
                "passed": endpoint_configured,
                "details": {"configured": endpoint_configured, "endpoint_url": redacted_endpoint},
            },
            {
                "name": "internal_registry_endpoint_url_scheme_supported",
                "passed": endpoint_scheme_supported,
                "details": {"supported_schemes": ["http", "https"], "endpoint_url": redacted_endpoint},
            },
            {
                "name": "internal_registry_endpoint_url_has_no_inline_secret_material",
                "passed": endpoint_inline_secret_material_absent,
                "details": {
                    "endpoint_url": redacted_endpoint,
                    "query_redacted": endpoint_query_present,
                    "userinfo_redacted": endpoint_userinfo_present,
                },
            },
            {
                "name": "internal_registry_method_supported",
                "passed": method_supported,
                "details": {"method": method, "supported_methods": sorted(_ALLOWED_METHODS)},
            },
            {
                "name": "internal_registry_content_type_configured",
                "passed": content_type_configured,
                "details": {"configured": content_type_configured},
            },
            {
                "name": "internal_registry_apply_intent_reviewed",
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
        request_body = _publication_request_body(
            provider_id=self.provider_id,
            package=package,
            package_digest=package_digest,
            identity=identity,
            publication_contract=self.publication_contract,
            package_name=self.package_name,
            package_version=self.package_version,
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
            response = self._publish(endpoint, request_body, method)
            response_status_code = response.status_code
            request_error = _redact_request_error_for_metadata(response.error)
            delivered = bool(response_status_code is not None and 200 <= response_status_code < 300)
            checks.append(
                {
                    "name": "internal_registry_publication_successful",
                    "passed": delivered,
                    "details": {
                        "status_code": response_status_code,
                        "request_error": request_error,
                        "endpoint_url": redacted_endpoint,
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
                ["review_internal_registry_external_delivery_result"]
                if delivered
                else ["approve_internal_registry_delivery_before_apply"]
                if dry_run and not blocking_reasons
                else ["fix_internal_registry_external_delivery_blockers"]
            ),
            created_at=created_at,
            metadata={
                "scope": "internal-registry-external-delivery-provider-baseline",
                "package_metadata_recorded": False,
                "package_metadata_key_count": len(package.metadata),
                "automatic_delivery": False,
                "publishes_externally": delivered,
                "dry_run_side_effect_free": True,
                "network_attempted": request_attempted,
                "publication_contract": str(self.publication_contract or ""),
                "registry_endpoint_url": redacted_endpoint,
                "registry_endpoint_query_redacted": endpoint_query_present,
                "registry_endpoint_userinfo_redacted": endpoint_userinfo_present,
                "namespace_digest_sha256": identity["namespace_digest_sha256"],
                "project_digest_sha256": identity["project_digest_sha256"],
                "repository_digest_sha256": identity["repository_digest_sha256"],
                "namespace_recorded": False,
                "project_recorded": False,
                "repository_recorded": False,
                "package_name_digest_sha256": _optional_digest(self.package_name),
                "package_version_digest_sha256": _optional_digest(self.package_version),
                "request_method": method,
                "request_body_digest_sha256": request_body_digest,
                "request_body_bytes": len(request_body),
                "request_status_code": response_status_code,
                "request_error": request_error,
                "request_headers_recorded": False,
                "response_body_recorded": False,
                "response_headers_recorded": False,
                "provider_config_values_recorded": False,
                "configured_header_count": len(self.headers),
                "auth_configured": bool(str(self.auth_token or "").strip()),
                "auth_value_recorded": False,
                "content_type": str(self.content_type or ""),
                "timeout_seconds": float(self.timeout_seconds),
                "http_library": "urllib.request" if self.http_requester is None else "injected-http-requester",
                "limitations": [
                    "baseline_http_post_or_put_json_only",
                    "does_not_implement_registry_specific_sdk_contract",
                    "does_not_record_request_or_response_payloads",
                    "does_not_record_raw_private_namespace_project_or_repository",
                    "apply_requires_package_mode_apply_and_explicit_review_approval",
                ],
            },
        )

    def _publish(self, url: str, body: bytes, method: str) -> InternalRegistryHttpResponse:
        request_headers = {
            "Content-Type": str(self.content_type or "application/json"),
            "Accept": "application/json, */*;q=0.1",
            "User-Agent": "reverse-deepagent-internal-registry-provider/0.1",
            **{str(name): str(value) for name, value in self.headers.items()},
        }
        if self.auth_token:
            request_headers.setdefault("Authorization", f"Bearer {self.auth_token}")
        requester = self.http_requester or _stdlib_http_requester
        return requester(url, body, request_headers, method, float(self.timeout_seconds))


def create_internal_registry_external_delivery_provider(**kwargs: Any) -> InternalRegistryExternalDeliveryProvider:
    """Factory used by ExternalDeliveryProviderRegistry.

    Registry metadata listing must not call this function. Tests track factory
    invocations to keep the entry-point side-effect boundary explicit.
    """

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    return InternalRegistryExternalDeliveryProvider(
        registry_endpoint_url=kwargs.get("registry_endpoint_url"),
        namespace=kwargs.get("namespace"),
        project=kwargs.get("project"),
        repository=kwargs.get("repository"),
        package_name=kwargs.get("package_name"),
        package_version=kwargs.get("package_version"),
        publication_contract=kwargs.get("publication_contract", "reviewed-json-package"),
        method=kwargs.get("method", "POST"),
        content_type=kwargs.get("content_type", "application/json"),
        headers=kwargs.get("headers", {}),
        auth_token=kwargs.get("auth_token"),
        timeout_seconds=kwargs.get("timeout_seconds", 10.0),
        approve_internal_registry_delivery=str(kwargs.get("approve_internal_registry_delivery", "false")).lower() in ("true", "1", "yes"),
        http_requester=kwargs.get("http_requester"),
        provider_id=kwargs.get("provider_id", INTERNAL_REGISTRY_EXTERNAL_DELIVERY_PROVIDER_ID),
    )


def external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    return ExternalDeliveryProviderRegistration(
        provider_id=INTERNAL_REGISTRY_EXTERNAL_DELIVERY_PROVIDER_ID,
        aliases=INTERNAL_REGISTRY_EXTERNAL_DELIVERY_PROVIDER_ALIASES,
        capabilities=ExternalDeliveryProviderCapabilities(
            provider_id=INTERNAL_REGISTRY_EXTERNAL_DELIVERY_PROVIDER_ID,
            display_name="Internal artifact registry external delivery",
            transport="internal-artifact-registry",
            supports_external_delivery=True,
            review_only=False,
            metadata={
                "side_effect_free": True,
                "dry_run_side_effect_free": True,
                "writes_external_delivery_result": True,
                "publishes_externally": True,
                "external_boundary": "internal-artifact-registry-http",
                "sends_http_post": True,
                "sends_http_put": True,
                "cloud_sdk_required": False,
                "third_party_sdk_required": False,
                "apply_requires_explicit_review_approval": True,
                "endpoint_inline_material_blocked_by_default": True,
                "records_request_body": False,
                "records_request_headers": False,
                "records_response_body": False,
                "records_response_headers": False,
                "records_raw_path_components": False,
            },
        ),
        factory=create_internal_registry_external_delivery_provider,
    )


def factory_invocation_count() -> int:
    return _FACTORY_INVOCATION_COUNT


def _publication_request_body(
    *,
    provider_id: str,
    package: ExternalDeliveryPackage,
    package_digest: str,
    identity: dict[str, Any],
    publication_contract: str,
    package_name: str | None,
    package_version: str | None,
    created_at: str,
) -> bytes:
    payload = {
        "provider_id": provider_id,
        "transaction_id": package.transaction_id,
        "created_at": created_at,
        "publication_contract": publication_contract,
        "package_digest_sha256": package_digest,
        "package_name_digest_sha256": _optional_digest(package_name),
        "package_version_digest_sha256": _optional_digest(package_version),
        "identity": identity,
        "delivery_package": package.to_dict(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _identity_summary(*, namespace: str | None, project: str | None, repository: str | None) -> dict[str, Any]:
    return {
        "namespace_configured": bool(str(namespace or "").strip()),
        "project_configured": bool(str(project or "").strip()),
        "repository_configured": bool(str(repository or "").strip()),
        "namespace_digest_sha256": _optional_digest(namespace),
        "project_digest_sha256": _optional_digest(project),
        "repository_digest_sha256": _optional_digest(repository),
        "raw_values_recorded": False,
    }


def _normalise_endpoint(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = re.sub(r"/+$", "", parsed.path or "")
    return urllib.parse.urlunsplit((scheme, netloc, path, parsed.query, ""))


def _stdlib_http_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float) -> InternalRegistryHttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - explicit reviewed provider target.
            return InternalRegistryHttpResponse(status_code=int(response.status), error=None, body=b"")
    except urllib.error.HTTPError as exc:
        return InternalRegistryHttpResponse(status_code=int(exc.code), error=f"http_error:{int(exc.code)}", body=b"")
    except urllib.error.URLError as exc:
        return InternalRegistryHttpResponse(status_code=None, error=f"url_error:{exc.reason}", body=b"")
    except TimeoutError:
        return InternalRegistryHttpResponse(status_code=None, error="timeout", body=b"")


def _json_payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _optional_digest(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _redact_request_error_for_metadata(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    http_match = re.fullmatch(r"http_error:(\d{3})", text)
    if http_match:
        return f"http_error:{http_match.group(1)}"
    if text == "timeout":
        return "timeout"
    return "redacted_request_error"


def _http_scheme_supported(url: str) -> bool:
    if not url:
        return False
    return urllib.parse.urlsplit(url).scheme.lower() in {"http", "https"}


def _url_has_query(url: str) -> bool:
    return bool(urllib.parse.urlsplit(url).query)


def _url_has_userinfo(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return bool(parsed.username or parsed.password)


def _redact_url_for_metadata(url: str) -> str | None:
    if not url:
        return None
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    path = parsed.path or ""
    redacted_path = "/<redacted-registry-endpoint>" if path and path != "/" else path
    return urllib.parse.urlunsplit((parsed.scheme.lower(), host.lower(), redacted_path, "", ""))
