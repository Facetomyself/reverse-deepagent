# reverse-deepagent-external-delivery-provider-internal-registry

Internal artifact registry `ExternalDeliveryProvider` plugin baseline for `reverse-deepagent`.

The package exposes provider id `internal-registry` through the
`reverse_deepagent.external_delivery_providers` Python entry-point group. Aliases
include `artifact-registry` and `internal-artifacts`.

## Safety contract

- Registration and capability metadata are side-effect free: no environment
  reads, no client creation, no file reads, and no network access.
- Dry-run never performs network I/O and returns a reviewable publication plan.
- Apply mode requires both `package.mode == "apply"` and
  `approve_internal_registry_delivery=True`.
- The provider uses stdlib `urllib.request` by default, or an injectable
  requester seam for tests/integrators. It does not depend on a registry SDK.
- Endpoint URLs containing userinfo or query material are blocked by default.
- Result metadata records only redacted endpoint URLs, digests, counts, booleans,
  status codes, and coarse identifiers. It never records raw configured header
  values, request bodies, response bodies, response headers, tokens, query
  strings, URL userinfo, or raw private namespace/project/repository paths.

## Minimal config

```python
provider = create_internal_registry_external_delivery_provider(
    registry_endpoint_url="https://registry.example.test/api/artifacts",
    namespace="team/private-namespace",
    project="reverse-deepagent",
    repository="reviewed-deliveries",
    approve_internal_registry_delivery=True,
)
```

This baseline intentionally supports a minimal reviewed HTTP `POST`/`PUT` JSON
publication contract only. It does not implement registry-specific package
metadata schemas, auth discovery, retries, uploads of arbitrary binary blobs, or
SDK client lifecycle management.
