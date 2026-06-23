# reverse-deepagent-browser-provider-antidetect-cdp

Vendor-neutral AntiDetect hosted CDP BrowserProvider baseline for `reverse-deepagent`.

This package is intentionally not tied to one vendor SDK. It models the safe seam for anti-detect browsers, enterprise browser pools, and hosted browser services that expose a reviewed Chrome DevTools Protocol endpoint after an operator or upstream service has allocated a session/profile.

## Entry point

```toml
[project.entry-points."reverse_deepagent.browser_providers"]
antidetect-cdp = "reverse_deepagent_browser_provider_antidetect_cdp:browser_provider_registration"
```

Aliases include `anti-detect-cdp`, `antidetect-hosted-cdp`, `anti-detect-hosted-cdp`, and `vendor-antidetect-cdp`.

## Side-effect boundary

Metadata-only discovery is safe:

- does not call the provider factory;
- does not read environment variables, API keys, profile cookies, proxy credentials, or vendor secrets;
- does not allocate a vendor browser session;
- does not probe CDP endpoints or open sockets;
- does not start a local or hosted browser.

`start()` is intentionally review-gated in this vendor-neutral baseline: it only consumes an injected allocator seam or an already reviewed allocation descriptor when `approve_antidetect_allocation=True` is passed by the caller. Without that explicit approval it returns a structured unavailable error and does not call allocators, read secrets, contact vendors, or start browsers. Callers may still allocate or approve the vendor anti-detect browser session outside core, then attach with `connect()` using a reviewed endpoint.

## Runtime configuration

`connect()` supports two explicit endpoint modes:

- `browser_url` / `cdp_browser_url` / `antidetect_browser_url`: HTTP DevTools endpoint delegated to core `RemoteCDPProvider`.
- `browser_ws_url` / `cdp_browser_ws_url` / `antidetect_browser_ws_url`: direct browser-level CDP WebSocket endpoint using a minimal provider-neutral wrapper.

Optional non-secret allocation metadata:

- `allocation_id` / `antidetect_allocation_id`
- `profile_id` / `antidetect_profile_id`
- `tenant_label`

Review-gated allocation handoff:

- `allocation_requester` / `antidetect_allocation_requester`: injected callable that receives a caller-provided allocation request and returns a reviewed CDP endpoint descriptor.
- `allocation_request` / `antidetect_allocation_request`: caller-provided request metadata passed only to the injected allocator during approved `start()`.
- `reviewed_allocation_result` / `allocation_result` / `antidetect_allocation_result`: pre-reviewed descriptor containing `browser_url`, `browser_ws_url`, or `endpoint`.
- `approve_antidetect_allocation=True`: mandatory approval flag for any `start()` allocation handoff.

Endpoint URLs, allocation ids, profile ids, endpoint query/userinfo, tokens, API keys, passwords, credentials, and opaque string payloads from allocation results are redacted in config summaries and event logs.

## Production-readiness metadata

The provider declares review-required production metadata covering:

- stealth / fingerprint policy;
- account and tenant boundary;
- endpoint security;
- allocation lifecycle;
- allocator contract and explicit approval requirements;
- profile persistence;
- proxy, extension, mobile emulation, and humanize ownership;
- attach-only lifecycle and local stop semantics.

This lets `reverse-agent-doctor --browser-provider-matrix` and BrowserProvider smoke acceptance review anti-detect provider readiness without contacting vendors, invoking allocators, or reading environment secrets.
