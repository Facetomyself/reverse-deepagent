# reverse-deepagent-external-delivery-provider-gitlab-release

Optional GitLab Release `ExternalDeliveryProvider` plugin package for
`reverse-deepagent`. It is intentionally small and stdlib-only so the provider
can be reviewed without adding a GitLab SDK dependency.

## Entry point

The package exposes metadata through the
`reverse_deepagent.external_delivery_providers` Python entry-point group:

```toml
[project.entry-points."reverse_deepagent.external_delivery_providers"]
gitlab-release = "reverse_deepagent_external_delivery_provider_gitlab_release:external_delivery_provider_registration"
```

Loading provider metadata is side-effect free: it does not call the provider
factory, read credentials, open sockets, upload artifacts, or contact GitLab.

## Provider behavior

Provider id: `gitlab-release`

Aliases: `gl-release`, `gitlab-release-assets`

- Dry-run returns a planned GitLab Release request and never performs network IO.
- Optional binary asset upload is supported through the conservative GitLab
  Project Uploads API followed by a GitLab Release asset link request. This is
  opt-in only.
- Dry-run with an asset upload request returns an upload plan only. It does not
  open sockets and does not read `upload_asset_path` contents.
- Apply mode requires a local delivery package with `package.mode == "apply"`.
- Apply mode also requires `approve_gitlab_release_delivery=True` in provider
  construction kwargs. Without that explicit review/apply intent, the provider
  returns a structured blocked result and does not perform network IO.
- Applying a binary asset upload additionally requires
  `approve_gitlab_release_asset_upload=True` and executable artifact input via
  `upload_asset_bytes` or `upload_asset_path`. A source descriptor without bytes
  or a readable path is treated as a review/planning seam and will not execute
  upload side effects.
- The default HTTP implementation uses Python stdlib `urllib.request`; tests or
  integrators can inject `http_requester` to mock requests.
- Result metadata records only redacted endpoints, status codes, request body
  digests, upload/link status codes, and policy summaries. It does not record
  access tokens, request headers, response headers, response bodies,
  credentialed URLs, upload response URLs, project raw paths, or query strings.

## Example

```python
from reverse_deepagent.delivery import ExternalDeliveryProviderRegistry
from reverse_deepagent_external_delivery_provider_gitlab_release import (
    external_delivery_provider_registration,
)

registry = ExternalDeliveryProviderRegistry()
registry.register(external_delivery_provider_registration())

provider = registry.create(
    "gitlab-release",
    project_path="group/project",
    tag_name="v0.1.0",
    access_token="glpat-...",
    approve_gitlab_release_delivery=True,
)
```

Optional binary asset upload:

```python
provider = registry.create(
    "gitlab-release",
    project_path="group/project",
    tag_name="v0.1.0",
    access_token="glpat-...",
    approve_gitlab_release_delivery=True,
    approve_gitlab_release_asset_upload=True,
    upload_asset_path="/reviewed/delivery/agent.bundle.tgz",
    upload_asset_name="agent.bundle.tgz",
)
```

If release creation succeeds but upload or link creation fails, the provider
returns a conservative blocked result with `release_record_created=True` and
`external_delivery_performed=False`, so reviewers know an external side effect
has occurred before deciding whether to retry or reconcile manually.

Do not place secrets in `project_path`, `release_name`, `asset_name`, or other
review-visible fields. The provider keeps credential values out of metadata, but
callers are still responsible for passing configuration through secret-aware
runtime channels.
