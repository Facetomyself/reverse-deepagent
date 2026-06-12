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
- Apply mode requires a local delivery package with `package.mode == "apply"`.
- Apply mode also requires `approve_gitlab_release_delivery=True` in provider
  construction kwargs. Without that explicit review/apply intent, the provider
  returns a structured blocked result and does not perform network IO.
- The default HTTP implementation uses Python stdlib `urllib.request`; tests or
  integrators can inject `http_requester` to mock requests.
- Result metadata records only redacted endpoints, status codes, request body
  digests, and policy summaries. It does not record access tokens, request
  headers, response headers, response bodies, credentialed URLs, or query
  strings.

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

Do not place secrets in `project_path`, `release_name`, `asset_name`, or other
review-visible fields. The provider keeps credential values out of metadata, but
callers are still responsible for passing configuration through secret-aware
runtime channels.
