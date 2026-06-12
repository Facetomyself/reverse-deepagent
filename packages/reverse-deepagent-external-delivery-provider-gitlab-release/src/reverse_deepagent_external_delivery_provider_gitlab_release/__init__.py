from __future__ import annotations

from dataclasses import dataclass
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

GITLAB_RELEASE_EXTERNAL_DELIVERY_PROVIDER_ID = "gitlab-release"
GITLAB_RELEASE_EXTERNAL_DELIVERY_PROVIDER_ALIASES = ("gl-release", "gitlab-release-assets")
_FACTORY_INVOCATION_COUNT = 0


@dataclass(frozen=True, slots=True)
class GitLabReleaseHttpResponse:
    """Minimal secret-safe response shape returned by the HTTP seam."""

    status_code: int | None
    error: str | None = None
    body: bytes = b""


GitLabReleaseHttpRequester = Callable[[str, bytes, dict[str, str], str, float], GitLabReleaseHttpResponse]


@dataclass(frozen=True)
class GitLabReleaseExternalDeliveryProvider:
    """GitLab Release external delivery provider baseline.

    Dry-run is side-effect free. Apply mode creates one GitLab Release through
    the GitLab REST API using a stdlib HTTP seam. Runtime credentials are used
    only for request headers and are never serialized into result metadata.
    """

    project_path: str | None = None
    tag_name: str | None = None
    release_name: str | None = None
    asset_name: str | None = None
    access_token: str | None = None
    api_base_url: str = "https://gitlab.com/api/v4"
    timeout_seconds: float = 10.0
    approve_gitlab_release_delivery: bool = False
    release_description: str | None = None
    http_requester: GitLabReleaseHttpRequester | None = None
    provider_id: str = GITLAB_RELEASE_EXTERNAL_DELIVERY_PROVIDER_ID

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
        project_path = _normalize_project_path(self.project_path)
        project_digest = _optional_digest(project_path)
        tag_name = str(self.tag_name or "").strip()
        release_name = str(self.release_name or tag_name or "").strip()
        asset_name = _safe_asset_name(self.asset_name or f"reverse-deepagent-{package.transaction_id}.json")
        api_base_url = _normalize_api_base_url(self.api_base_url)
        release_url = _gitlab_release_url(api_base_url, project_path)
        redacted_api_base_url = _redact_url_for_metadata(api_base_url)
        redacted_release_url = _redact_url_for_metadata(release_url)
        api_query_present = _url_has_query(api_base_url)
        api_credentials_present = _url_has_credentials(api_base_url)
        api_inline_secret_material_absent = not (api_query_present or api_credentials_present)
        local_ready = not package.local_errors
        auth_configured = bool(str(self.access_token or "").strip())
        api_scheme_supported = _http_scheme_supported(api_base_url)
        package_mode_apply = package.mode == "apply"
        explicit_apply_approval = bool(self.approve_gitlab_release_delivery)
        apply_allowed = bool(dry_run or (package_mode_apply and explicit_apply_approval))
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_errors": package.local_errors},
            },
            {
                "name": "gitlab_project_configured",
                "passed": bool(project_path),
                "details": {"configured": bool(project_path), "project_path_digest_sha256": project_digest},
            },
            {
                "name": "gitlab_release_tag_configured",
                "passed": bool(tag_name),
                "details": {"configured": bool(tag_name)},
            },
            {
                "name": "gitlab_auth_configured",
                "passed": auth_configured,
                "details": {"configured": auth_configured},
            },
            {
                "name": "gitlab_api_url_scheme_supported",
                "passed": api_scheme_supported,
                "details": {"supported_schemes": ["http", "https"], "api_base_url": redacted_api_base_url},
            },
            {
                "name": "gitlab_api_url_has_no_inline_secret_material",
                "passed": api_inline_secret_material_absent,
                "details": {
                    "api_base_url": redacted_api_base_url,
                    "query_redacted": api_query_present,
                    "credentials_redacted": api_credentials_present,
                },
            },
            {
                "name": "gitlab_release_apply_intent_reviewed",
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
        release_status_code: int | None = None
        release_error: str | None = None
        request_attempted = False
        request_body = _release_request_body(
            provider_id=self.provider_id,
            package=package,
            package_digest=package_digest,
            tag_name=tag_name,
            release_name=release_name,
            asset_name=asset_name,
            created_at=created_at,
            description=self.release_description,
        )
        request_body_digest = hashlib.sha256(request_body).hexdigest()
        delivered = False
        if dry_run:
            status = "planned" if not preflight_blocking_reasons else "blocked"
            blocking_reasons = preflight_blocking_reasons
        elif preflight_blocking_reasons:
            status = "blocked"
            blocking_reasons = preflight_blocking_reasons
        else:
            request_attempted = True
            response = self._create_release(release_url, request_body)
            release_status_code = response.status_code
            release_error = response.error
            delivered = bool(release_status_code is not None and 200 <= release_status_code < 300)
            checks.append(
                {
                    "name": "gitlab_release_create_successful",
                    "passed": delivered,
                    "details": {
                        "status_code": release_status_code,
                        "request_error": release_error,
                        "target_url": redacted_release_url,
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
                ["review_gitlab_release_external_delivery_result"]
                if delivered
                else ["approve_gitlab_release_delivery_before_apply"]
                if dry_run and not blocking_reasons
                else ["fix_gitlab_release_external_delivery_blockers"]
            ),
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "gitlab-release-external-delivery-provider-baseline",
                "automatic_delivery": False,
                "publishes_externally": delivered,
                "dry_run_side_effect_free": True,
                "network_attempted": request_attempted,
                "project_path_configured": bool(project_path),
                "project_path_digest_sha256": project_digest,
                "project_path_recorded": False,
                "tag_name": tag_name or None,
                "release_name": release_name or None,
                "asset_name": asset_name,
                "api_base_url": redacted_api_base_url,
                "release_api_url": redacted_release_url,
                "api_query_redacted": api_query_present,
                "api_credentials_redacted": api_credentials_present,
                "request_body_digest_sha256": request_body_digest,
                "request_status_code": release_status_code,
                "request_error": release_error,
                "request_headers_recorded": False,
                "response_body_recorded": False,
                "response_headers_recorded": False,
                "provider_config_values_recorded": False,
                "http_library": "urllib.request" if self.http_requester is None else "injected-http-requester",
                "limitations": [
                    "baseline_creates_gitlab_release_record",
                    "does_not_upload_binary_assets_yet",
                    "apply_requires_package_mode_apply_and_explicit_review_approval",
                ],
            },
        )

    def _create_release(self, url: str, body: bytes) -> GitLabReleaseHttpResponse:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "reverse-deepagent-gitlab-release-provider/0.1",
        }
        access_value = str(self.access_token or "").strip()
        if access_value:
            headers["PRIVATE-TOKEN"] = access_value
        requester = self.http_requester or _stdlib_http_requester
        return requester(url, body, headers, "POST", float(self.timeout_seconds))


def gitlab_release_external_delivery_provider_capabilities() -> ExternalDeliveryProviderCapabilities:
    """Return side-effect-free, non-secret GitLab Release provider metadata."""

    return ExternalDeliveryProviderCapabilities(
        provider_id=GITLAB_RELEASE_EXTERNAL_DELIVERY_PROVIDER_ID,
        display_name="GitLab Release external delivery",
        transport="gitlab-release",
        supports_external_delivery=True,
        review_only=False,
        metadata={
            "side_effect_free": False,
            "dry_run_side_effect_free": True,
            "writes_external_delivery_result": True,
            "publishes_externally": True,
            "external_boundary": "gitlab-release",
            "sends_http_post": True,
            "cloud_sdk_required": False,
            "records_request_headers": False,
            "records_response_body": False,
            "records_response_headers": False,
            "apply_requires_package_mode_apply": True,
            "apply_requires_explicit_review_approval": True,
            "metadata_loading_invokes_factory": False,
        },
    )


def create_gitlab_release_external_delivery_provider(**kwargs: Any) -> GitLabReleaseExternalDeliveryProvider:
    """Factory used by ExternalDeliveryProviderRegistry.

    Registry metadata listing must not call this function. Tests track factory
    invocations to keep the entry-point side-effect boundary explicit.
    """

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    return GitLabReleaseExternalDeliveryProvider(
        project_path=kwargs.get("project_path"),
        tag_name=kwargs.get("tag_name"),
        release_name=kwargs.get("release_name"),
        asset_name=kwargs.get("asset_name"),
        access_token=kwargs.get("access_token"),
        api_base_url=kwargs.get("api_base_url", "https://gitlab.com/api/v4"),
        timeout_seconds=kwargs.get("timeout_seconds", 10.0),
        approve_gitlab_release_delivery=bool(kwargs.get("approve_gitlab_release_delivery", False)),
        release_description=kwargs.get("release_description"),
        http_requester=kwargs.get("http_requester"),
    )


def external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    """Return the GitLab Release registration without creating providers."""

    return ExternalDeliveryProviderRegistration(
        provider_id=GITLAB_RELEASE_EXTERNAL_DELIVERY_PROVIDER_ID,
        aliases=GITLAB_RELEASE_EXTERNAL_DELIVERY_PROVIDER_ALIASES,
        capabilities=gitlab_release_external_delivery_provider_capabilities(),
        factory=create_gitlab_release_external_delivery_provider,
    )


def factory_invocation_count() -> int:
    return _FACTORY_INVOCATION_COUNT


def _stdlib_http_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float) -> GitLabReleaseHttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read(0)
            return GitLabReleaseHttpResponse(status_code=int(response.status), error=None, body=b"")
    except urllib.error.HTTPError as exc:
        return GitLabReleaseHttpResponse(status_code=int(exc.code), error="HTTPError", body=b"")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return GitLabReleaseHttpResponse(status_code=None, error=exc.__class__.__name__, body=b"")


def _release_request_body(
    *,
    provider_id: str,
    package: ExternalDeliveryPackage,
    package_digest: str,
    tag_name: str,
    release_name: str,
    asset_name: str,
    created_at: str,
    description: str | None,
) -> bytes:
    summary = {
        "provider_id": provider_id,
        "transaction_id": package.transaction_id,
        "package_digest_sha256": package_digest,
        "delivery_status": package.status,
        "delivery_mode": package.mode,
        "delivered_artifact_count": len(package.delivered_artifacts),
        "planned_artifact_count": len(package.planned_artifacts),
        "created_at": created_at,
        "asset_name": asset_name,
    }
    release_description = (description or _default_release_description(summary)).strip()
    payload = {
        "tag_name": tag_name,
        "name": release_name or tag_name,
        "description": release_description,
        "milestones": [],
        "assets": {"links": []},
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _default_release_description(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "reverse-deepagent external delivery package summary",
            f"transaction_id: {summary['transaction_id']}",
            f"package_digest_sha256: {summary['package_digest_sha256']}",
            f"delivery_status: {summary['delivery_status']}",
            f"delivery_mode: {summary['delivery_mode']}",
            f"delivered_artifact_count: {summary['delivered_artifact_count']}",
            f"planned_artifact_count: {summary['planned_artifact_count']}",
        ]
    )


def _json_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_digest(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_project_path(value: str | None) -> str:
    project_path = str(value or "").strip().strip("/")
    if project_path.endswith(".git"):
        project_path = project_path[:-4]
    project_path = re.sub(r"\s+", "", project_path)
    return project_path


def _normalize_api_base_url(value: str | None) -> str:
    raw = str(value or "https://gitlab.com/api/v4").strip() or "https://gitlab.com/api/v4"
    return raw.rstrip("/")


def _gitlab_release_url(api_base_url: str, project_path: str) -> str:
    if not api_base_url or not project_path:
        return ""
    quoted_project = urllib.parse.quote(project_path, safe="")
    return f"{api_base_url}/projects/{quoted_project}/releases"


def _safe_asset_name(value: str) -> str:
    name = str(value or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."}:
        return "reverse-deepagent-delivery-package.json"
    return name


def _http_scheme_supported(value: str) -> bool:
    return urllib.parse.urlsplit(value).scheme in {"http", "https"}


def _url_has_query(value: str) -> bool:
    return bool(value and urllib.parse.urlsplit(value).query)


def _url_has_credentials(value: str) -> bool:
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
    path = re.sub(r"(/projects/)[^/]+(/releases(?:/.*)?$)", r"\1<redacted>\2", parts.path)
    redacted = urllib.parse.urlunsplit((parts.scheme, netloc, path, "", ""))
    return redacted or None
