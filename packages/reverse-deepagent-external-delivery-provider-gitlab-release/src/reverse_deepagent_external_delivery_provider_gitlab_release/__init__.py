from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import uuid
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
class GitLabReleaseAssetUploadPlan:
    """Review-gated binary asset upload descriptor.

    The plan deliberately stores source shape and safe names only. Dry-run must
    not read filesystem bytes or serialize request bodies / upload URLs.
    """

    requested: bool
    name: str | None
    source_type: str | None
    source_descriptor_present: bool
    content_type: str
    source_size_bytes: int | None = None
    source_digest_sha256: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "name": self.name,
            "source_type": self.source_type,
            "source_descriptor_present": self.source_descriptor_present,
            "content_type": self.content_type,
            "source_size_bytes": self.source_size_bytes,
            "source_digest_sha256": self.source_digest_sha256,
        }


@dataclass(frozen=True)
class GitLabReleaseExternalDeliveryProvider:
    """GitLab Release external delivery provider baseline.

    Dry-run is side-effect free. Apply mode creates one GitLab Release through
    the GitLab REST API using a stdlib HTTP seam. Optional binary asset upload
    uses GitLab Project Uploads followed by Release asset link creation, but only
    after a second explicit review approval. Runtime credentials and response
    bodies are never serialized into result metadata.
    """

    project_path: str | None = None
    tag_name: str | None = None
    release_name: str | None = None
    asset_name: str | None = None
    access_token: str | None = None
    api_base_url: str = "https://gitlab.com/api/v4"
    timeout_seconds: float = 10.0
    approve_gitlab_release_delivery: bool = False
    approve_gitlab_release_asset_upload: bool = False
    release_description: str | None = None
    upload_asset_path: str | None = None
    upload_asset_bytes: bytes | bytearray | memoryview | None = None
    upload_asset_source_descriptor: dict[str, Any] | str | None = None
    upload_asset_name: str | None = None
    upload_asset_content_type: str = "application/octet-stream"
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
        release_asset_name = _safe_asset_name(self.asset_name or f"reverse-deepagent-{package.transaction_id}.json")
        api_base_url = _normalize_api_base_url(self.api_base_url)
        release_url = _gitlab_release_url(api_base_url, project_path)
        upload_url = _gitlab_upload_url(api_base_url, project_path)
        link_url = _gitlab_release_link_url(api_base_url, project_path, tag_name)
        redacted_api_base_url = _redact_url_for_metadata(api_base_url)
        redacted_release_url = _redact_url_for_metadata(release_url)
        redacted_upload_url = _redact_url_for_metadata(upload_url)
        redacted_link_url = _redact_url_for_metadata(link_url)
        api_query_present = _url_has_query(api_base_url)
        api_credentials_present = _url_has_credentials(api_base_url)
        api_inline_secret_material_absent = not (api_query_present or api_credentials_present)
        local_ready = not package.local_errors
        auth_configured = bool(str(self.access_token or "").strip())
        api_scheme_supported = _http_scheme_supported(api_base_url)
        package_mode_apply = package.mode == "apply"
        explicit_apply_approval = bool(self.approve_gitlab_release_delivery)
        explicit_asset_upload_approval = bool(self.approve_gitlab_release_asset_upload)
        asset_plan = self._build_asset_upload_plan(dry_run=dry_run)
        apply_allowed = bool(dry_run or (package_mode_apply and explicit_apply_approval))
        asset_upload_allowed = bool(
            (not asset_plan.requested)
            or dry_run
            or (package_mode_apply and explicit_apply_approval and explicit_asset_upload_approval)
        )
        asset_source_executable = bool(
            (not asset_plan.requested)
            or dry_run
            or self.upload_asset_bytes is not None
            or _asset_path_is_executable_file(self.upload_asset_path)
        )
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
            {
                "name": "gitlab_release_asset_upload_reviewed",
                "passed": asset_upload_allowed,
                "details": {
                    "required_for_asset_upload_apply": True,
                    "asset_upload_requested": asset_plan.requested,
                    "dry_run": dry_run,
                    "package_mode_apply": package_mode_apply,
                    "explicit_release_approval": explicit_apply_approval,
                    "explicit_asset_upload_approval": explicit_asset_upload_approval,
                },
            },
            {
                "name": "gitlab_release_asset_upload_source_available",
                "passed": (not asset_plan.requested) or asset_plan.source_descriptor_present,
                "details": {
                    "asset_upload_requested": asset_plan.requested,
                    "source_type": asset_plan.source_type,
                    "source_descriptor_present": asset_plan.source_descriptor_present,
                },
            },
            {
                "name": "gitlab_release_asset_upload_executable_source_available",
                "passed": asset_source_executable,
                "details": {
                    "required_for_asset_upload_apply": True,
                    "asset_upload_requested": asset_plan.requested,
                    "dry_run": dry_run,
                    "source_type": asset_plan.source_type,
                    "file_content_read": False,
                },
            },
        ]
        preflight_blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        release_status_code: int | None = None
        release_error: str | None = None
        upload_status_code: int | None = None
        upload_error: str | None = None
        link_status_code: int | None = None
        link_error: str | None = None
        release_request_attempted = False
        upload_request_attempted = False
        link_request_attempted = False
        upload_response_body_parsed = False
        upload_response_url_used_for_link = False
        release_created = False
        asset_uploaded = False
        asset_link_created = False
        asset_request_digest: str | None = None
        link_request_digest: str | None = None
        request_body = _release_request_body(
            provider_id=self.provider_id,
            package=package,
            package_digest=package_digest,
            tag_name=tag_name,
            release_name=release_name,
            asset_name=release_asset_name,
            created_at=created_at,
            description=self.release_description,
        )
        request_body_digest = hashlib.sha256(request_body).hexdigest()
        if dry_run:
            status = "planned" if not preflight_blocking_reasons else "blocked"
            blocking_reasons = preflight_blocking_reasons
        elif preflight_blocking_reasons:
            status = "blocked"
            blocking_reasons = preflight_blocking_reasons
        else:
            release_request_attempted = True
            response = self._create_release(release_url, request_body)
            release_status_code = response.status_code
            release_error = response.error
            release_created = bool(release_status_code is not None and 200 <= release_status_code < 300)
            checks.append(
                {
                    "name": "gitlab_release_create_successful",
                    "passed": release_created,
                    "details": {
                        "status_code": release_status_code,
                        "request_error": release_error,
                        "target_url": redacted_release_url,
                        "response_body_recorded": False,
                        "response_headers_recorded": False,
                    },
                }
            )
            if release_created and asset_plan.requested:
                try:
                    asset_bytes = self._load_asset_bytes_for_apply()
                    asset_bytes_loaded = True
                except (OSError, ValueError) as exc:
                    asset_bytes = b""
                    asset_bytes_loaded = False
                    upload_error = exc.__class__.__name__
                checks.append(
                    {
                        "name": "gitlab_release_asset_bytes_loaded",
                        "passed": asset_bytes_loaded,
                        "details": {
                            "source_type": asset_plan.source_type,
                            "file_content_recorded": False,
                        },
                    }
                )
                if asset_bytes_loaded:
                    asset_plan = GitLabReleaseAssetUploadPlan(
                        requested=True,
                        name=asset_plan.name,
                        source_type=asset_plan.source_type,
                        source_descriptor_present=asset_plan.source_descriptor_present,
                        content_type=asset_plan.content_type,
                        source_size_bytes=len(asset_bytes),
                        source_digest_sha256=hashlib.sha256(asset_bytes).hexdigest(),
                    )
                    upload_body, upload_headers, asset_request_digest = _multipart_upload_body(
                        asset_name=asset_plan.name or "reverse-deepagent-asset.bin",
                        asset_bytes=asset_bytes,
                        content_type=asset_plan.content_type,
                    )
                    upload_request_attempted = True
                    upload_response = self._upload_asset(upload_url, upload_body, upload_headers)
                    upload_status_code = upload_response.status_code
                    upload_error = upload_response.error
                    asset_uploaded = bool(upload_status_code is not None and 200 <= upload_status_code < 300)
                    uploaded_relative_url: str | None = None
                    if asset_uploaded:
                        uploaded_relative_url = _extract_upload_response_url(upload_response.body)
                        upload_response_body_parsed = uploaded_relative_url is not None
                        asset_uploaded = uploaded_relative_url is not None and _upload_response_url_is_safe_relative(uploaded_relative_url)
                        if not asset_uploaded and upload_error is None:
                            upload_error = "UnsafeOrMissingUploadUrl"
                else:
                    uploaded_relative_url = None
                checks.append(
                    {
                        "name": "gitlab_project_upload_successful",
                        "passed": asset_uploaded,
                        "details": {
                            "status_code": upload_status_code,
                            "request_error": upload_error,
                            "target_url": redacted_upload_url,
                            "response_body_recorded": False,
                            "response_headers_recorded": False,
                            "upload_url_query_or_credentials_rejected": upload_response_body_parsed and not asset_uploaded,
                        },
                    }
                )
                if asset_uploaded and uploaded_relative_url:
                    absolute_asset_url = _absolute_gitlab_project_asset_url(api_base_url, project_path, uploaded_relative_url)
                    link_body = _release_asset_link_request_body(asset_plan.name or release_asset_name, absolute_asset_url)
                    link_request_digest = hashlib.sha256(link_body).hexdigest()
                    upload_response_url_used_for_link = True
                    link_request_attempted = True
                    link_response = self._create_release_asset_link(link_url, link_body)
                    link_status_code = link_response.status_code
                    link_error = link_response.error
                    asset_link_created = bool(link_status_code is not None and 200 <= link_status_code < 300)
                    checks.append(
                        {
                            "name": "gitlab_release_asset_link_successful",
                            "passed": asset_link_created,
                            "details": {
                                "status_code": link_status_code,
                                "request_error": link_error,
                                "target_url": redacted_link_url,
                                "response_body_recorded": False,
                                "response_headers_recorded": False,
                            },
                        }
                    )
            blocking_reasons = [check["name"] for check in checks if not check["passed"]]
            fully_delivered = release_created and ((not asset_plan.requested) or asset_link_created)
            status = "delivered" if fully_delivered else "blocked"
        asset_upload_completed = bool(asset_plan.requested and asset_uploaded and asset_link_created)
        fully_delivered = bool(release_created and ((not asset_plan.requested) or asset_upload_completed))
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status=status,
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=fully_delivered,
            package_digest_sha256=package_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=_recommended_actions(
                status=status,
                dry_run=dry_run,
                asset_upload_requested=asset_plan.requested,
                release_created=release_created,
                asset_uploaded=asset_uploaded,
                asset_link_created=asset_link_created,
                blocking_reasons=blocking_reasons,
            ),
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "gitlab-release-external-delivery-provider-baseline",
                "automatic_delivery": False,
                "publishes_externally": fully_delivered,
                "release_record_created": release_created,
                "external_side_effects_performed": bool(release_request_attempted and release_created),
                "dry_run_side_effect_free": True,
                "network_attempted": bool(release_request_attempted or upload_request_attempted or link_request_attempted),
                "release_request_attempted": release_request_attempted,
                "asset_upload_request_attempted": upload_request_attempted,
                "asset_link_request_attempted": link_request_attempted,
                "project_path_configured": bool(project_path),
                "project_path_digest_sha256": project_digest,
                "project_path_recorded": False,
                "tag_name": tag_name or None,
                "release_name": release_name or None,
                "asset_name": release_asset_name,
                "binary_asset_upload": asset_plan.to_metadata(),
                "api_base_url": redacted_api_base_url,
                "release_api_url": redacted_release_url,
                "upload_api_url": redacted_upload_url,
                "release_asset_link_api_url": redacted_link_url,
                "api_query_redacted": api_query_present,
                "api_credentials_redacted": api_credentials_present,
                "request_body_digest_sha256": request_body_digest,
                "asset_upload_request_body_digest_sha256": asset_request_digest,
                "asset_link_request_body_digest_sha256": link_request_digest,
                "request_status_code": release_status_code,
                "asset_upload_status_code": upload_status_code,
                "asset_link_status_code": link_status_code,
                "request_error": release_error,
                "asset_upload_error": upload_error,
                "asset_link_error": link_error,
                "upload_response_body_parsed": upload_response_body_parsed,
                "upload_response_url_recorded": False,
                "upload_response_url_used_for_release_link": upload_response_url_used_for_link,
                "request_headers_recorded": False,
                "response_body_recorded": False,
                "response_headers_recorded": False,
                "provider_config_values_recorded": False,
                "http_library": "urllib.request" if self.http_requester is None else "injected-http-requester",
                "limitations": [
                    "baseline_creates_gitlab_release_record",
                    "optional_binary_asset_upload_uses_project_uploads_then_release_asset_link",
                    "dry_run_does_not_read_asset_file_or_perform_network_io",
                    "apply_requires_package_mode_apply_and_explicit_review_approval",
                    "asset_upload_apply_requires_second_explicit_review_approval",
                ],
            },
        )

    def _build_asset_upload_plan(self, *, dry_run: bool) -> GitLabReleaseAssetUploadPlan:
        requested = bool(
            self.upload_asset_path is not None
            or self.upload_asset_bytes is not None
            or self.upload_asset_source_descriptor is not None
            or self.upload_asset_name is not None
        )
        if not requested:
            return GitLabReleaseAssetUploadPlan(False, None, None, False, _safe_content_type(self.upload_asset_content_type))
        source_type: str | None = None
        descriptor_present = False
        size_bytes: int | None = None
        digest: str | None = None
        if self.upload_asset_bytes is not None:
            source_type = "bytes"
            descriptor_present = True
            if not dry_run:
                raw = bytes(self.upload_asset_bytes)
                size_bytes = len(raw)
                digest = hashlib.sha256(raw).hexdigest()
        elif self.upload_asset_path is not None:
            source_type = "path"
            descriptor_present = bool(str(self.upload_asset_path).strip())
        elif self.upload_asset_source_descriptor is not None:
            source_type = "source_descriptor"
            descriptor_present = True
        name = _safe_asset_name(self.upload_asset_name or self.asset_name or _asset_name_from_path(self.upload_asset_path) or "reverse-deepagent-asset.bin")
        return GitLabReleaseAssetUploadPlan(
            True,
            name,
            source_type,
            descriptor_present,
            _safe_content_type(self.upload_asset_content_type),
            size_bytes,
            digest,
        )

    def _load_asset_bytes_for_apply(self) -> bytes:
        if self.upload_asset_bytes is not None:
            return bytes(self.upload_asset_bytes)
        if self.upload_asset_path is not None and str(self.upload_asset_path).strip():
            return Path(self.upload_asset_path).expanduser().read_bytes()
        raise ValueError("gitlab_release_asset_upload_requires_artifact_bytes_or_path")

    def _create_release(self, url: str, body: bytes) -> GitLabReleaseHttpResponse:
        headers = _json_headers(self.access_token)
        requester = self.http_requester or _stdlib_http_requester
        return requester(url, body, headers, "POST", float(self.timeout_seconds))

    def _upload_asset(self, url: str, body: bytes, extra_headers: dict[str, str]) -> GitLabReleaseHttpResponse:
        headers = {
            "Accept": "application/json",
            "User-Agent": "reverse-deepagent-gitlab-release-provider/0.1",
            **extra_headers,
        }
        access_value = str(self.access_token or "").strip()
        if access_value:
            headers["PRIVATE-TOKEN"] = access_value
        requester = self.http_requester or _stdlib_http_requester
        return requester(url, body, headers, "POST", float(self.timeout_seconds))

    def _create_release_asset_link(self, url: str, body: bytes) -> GitLabReleaseHttpResponse:
        headers = _json_headers(self.access_token)
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
            "supports_binary_asset_upload": True,
            "asset_upload_flow": "project_uploads_api_then_release_asset_link",
            "asset_upload_dry_run_reads_file": False,
            "cloud_sdk_required": False,
            "records_request_headers": False,
            "records_response_body": False,
            "records_response_headers": False,
            "records_upload_url_query": False,
            "apply_requires_package_mode_apply": True,
            "apply_requires_explicit_review_approval": True,
            "asset_upload_apply_requires_explicit_review_approval": True,
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
        approve_gitlab_release_asset_upload=bool(kwargs.get("approve_gitlab_release_asset_upload", False)),
        release_description=kwargs.get("release_description"),
        upload_asset_path=kwargs.get("upload_asset_path"),
        upload_asset_bytes=kwargs.get("upload_asset_bytes"),
        upload_asset_source_descriptor=kwargs.get("upload_asset_source_descriptor"),
        upload_asset_name=kwargs.get("upload_asset_name"),
        upload_asset_content_type=kwargs.get("upload_asset_content_type", "application/octet-stream"),
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


def _release_asset_link_request_body(asset_name: str, asset_url: str) -> bytes:
    payload = {
        "name": asset_name,
        "url": asset_url,
        "link_type": "package",
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


def _gitlab_upload_url(api_base_url: str, project_path: str) -> str:
    if not api_base_url or not project_path:
        return ""
    quoted_project = urllib.parse.quote(project_path, safe="")
    return f"{api_base_url}/projects/{quoted_project}/uploads"


def _gitlab_release_link_url(api_base_url: str, project_path: str, tag_name: str) -> str:
    if not api_base_url or not project_path or not tag_name:
        return ""
    quoted_project = urllib.parse.quote(project_path, safe="")
    quoted_tag = urllib.parse.quote(tag_name, safe="")
    return f"{api_base_url}/projects/{quoted_project}/releases/{quoted_tag}/assets/links"


def _safe_asset_name(value: str) -> str:
    name = str(value or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."}:
        return "reverse-deepagent-delivery-package.json"
    return name


def _asset_name_from_path(value: str | None) -> str | None:
    if not value:
        return None
    return Path(str(value)).name


def _safe_content_type(value: str | None) -> str:
    candidate = str(value or "application/octet-stream").strip()
    if not candidate or any(ch in candidate for ch in "\r\n;"):
        return "application/octet-stream"
    return candidate


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
    path = re.sub(r"(/projects/)[^/]+(/(?:releases|uploads)(?:/.*)?$)", r"\1<redacted>\2", parts.path)
    redacted = urllib.parse.urlunsplit((parts.scheme, netloc, path, "", ""))
    return redacted or None


def _json_headers(access_token: str | None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "reverse-deepagent-gitlab-release-provider/0.1",
    }
    access_value = str(access_token or "").strip()
    if access_value:
        headers["PRIVATE-TOKEN"] = access_value
    return headers


def _multipart_upload_body(*, asset_name: str, asset_bytes: bytes, content_type: str) -> tuple[bytes, dict[str, str], str]:
    boundary = f"----reverse-deepagent-{uuid.uuid4().hex}"
    safe_name = _safe_asset_name(asset_name)
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="file"; filename="{_multipart_quote(safe_name)}"\r\n'
            f"Content-Type: {_safe_content_type(content_type)}\r\n\r\n"
        ).encode("utf-8"),
        asset_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    body = b"".join(parts)
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, hashlib.sha256(body).hexdigest()


def _multipart_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', "\\\"").replace("\r", "").replace("\n", "")


def _asset_path_is_executable_file(value: str | None) -> bool:
    if value is None or not str(value).strip():
        return False
    try:
        return Path(str(value)).expanduser().is_file()
    except OSError:
        return False


def _extract_upload_response_url(body: bytes) -> str | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    url = payload.get("url")
    if not isinstance(url, str):
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    return cleaned


def _upload_response_url_is_safe_relative(value: str) -> bool:
    parts = urllib.parse.urlsplit(value)
    return not (parts.scheme or parts.netloc or parts.query or parts.username or parts.password)


def _absolute_gitlab_project_asset_url(api_base_url: str, project_path: str, upload_response_url: str) -> str:
    upload_parts = urllib.parse.urlsplit(upload_response_url)
    if upload_parts.scheme and upload_parts.netloc:
        return urllib.parse.urlunsplit((upload_parts.scheme, upload_parts.netloc, upload_parts.path, "", ""))
    base = _gitlab_web_base_url(api_base_url)
    relative = upload_response_url if upload_response_url.startswith("/") else f"/{upload_response_url}"
    project_prefix = "/" + project_path.strip("/")
    if relative.startswith(project_prefix + "/"):
        path = relative
    else:
        path = project_prefix + relative
    return urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _gitlab_web_base_url(api_base_url: str) -> str:
    parts = urllib.parse.urlsplit(api_base_url)
    path = re.sub(r"/api/v\d+$", "", parts.path.rstrip("/"))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _recommended_actions(
    *,
    status: str,
    dry_run: bool,
    asset_upload_requested: bool,
    release_created: bool,
    asset_uploaded: bool,
    asset_link_created: bool,
    blocking_reasons: list[str],
) -> list[str]:
    if status == "delivered":
        return ["review_gitlab_release_external_delivery_result"]
    if dry_run and not blocking_reasons:
        actions = ["approve_gitlab_release_delivery_before_apply"]
        if asset_upload_requested:
            actions.append("approve_gitlab_release_asset_upload_before_apply")
        return actions
    if release_created and asset_upload_requested and not asset_link_created:
        if asset_uploaded:
            return ["review_gitlab_release_partial_asset_link_failure_before_retry"]
        return ["review_gitlab_release_partial_asset_upload_failure_before_retry"]
    return ["fix_gitlab_release_external_delivery_blockers"]
