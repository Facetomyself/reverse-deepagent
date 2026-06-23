# reverse-deepagent-external-delivery-provider-template

Template ExternalDeliveryProvider plugin package for `reverse-deepagent`.

This package shows the minimum shape for adding a replaceable external delivery
provider without changing core delivery code. Copy it when integrating S3, OSS,
GCS, GitLab Release, artifact registries, internal release systems, or other
vendor-specific publication surfaces.

## Entry point

The package exposes one registration through the
`reverse_deepagent.external_delivery_providers` Python entry-point group:

```toml
[project.entry-points."reverse_deepagent.external_delivery_providers"]
template-external-delivery = "reverse_deepagent_external_delivery_provider_template:external_delivery_provider_registration"
```

`external_delivery_provider_registration()` returns an
`ExternalDeliveryProviderRegistration` with serializable, non-secret capability
metadata and a provider factory. Loading metadata must not call the factory,
open sockets, upload artifacts, import heavy optional SDKs, or read credentials.

## Replace these pieces

- Change `TEMPLATE_EXTERNAL_DELIVERY_PROVIDER_ID` and aliases.
- Replace `TemplateExternalDeliveryProvider.deliver()` with real SDK or HTTP
  publication code.
- Keep dry-run side-effect free.
- Keep default duplicate-guard and idempotency behavior in core delivery unless
  you have an explicit reviewed reason to opt out.
- Never put tokens, cookies, passwords, presigned URLs, raw headers, or response
  bodies in capability metadata, result metadata, logs, or thrown exceptions.

The default template intentionally never publishes externally. Dry-run returns a
reviewable plan when the local delivery package is valid; apply mode returns a
structured blocker until an integrator replaces the provider with real delivery
logic and explicit review gates.
