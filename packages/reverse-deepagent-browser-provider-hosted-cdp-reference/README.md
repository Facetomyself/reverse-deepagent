# reverse-deepagent-browser-provider-hosted-cdp-reference

Reference hosted CDP BrowserProvider plugin package for `reverse-deepagent`.

This package is stronger than the copy-and-replace hosted CDP template: it models
an explicit hosted-browser lifecycle with allocation, attach, release, redacted
metadata, and idempotent cleanup. It is still not a real vendor integration. Use
it as a reference when building a browser-service, anti-detect browser, or
enterprise browser-pool provider outside core runtime.

## Entry point

The package declares the standard BrowserProvider entry point:

```toml
[project.entry-points."reverse_deepagent.browser_providers"]
hosted-cdp-reference = "reverse_deepagent_browser_provider_hosted_cdp_reference:browser_provider_registration"
```

Registration and metadata matrix paths are side-effect-free: they do not allocate
hosted sessions, open sockets, probe CDP endpoints, import vendor SDKs, launch
browsers, or call legacy MCP.

## Reference lifecycle

- `start()` performs an explicit reference allocation, then attaches to the CDP
  endpoint through the core `RemoteCDPProvider`.
- `connect()` attaches to an existing session or endpoint without claiming
  ownership unless an allocation is already active.
- `stop()` closes the delegate provider and releases only an owned allocation.
- Repeated `stop()` calls are safe and do not duplicate release events.

The built-in allocator is intentionally in-memory and test-oriented. Real
providers should replace it with their vendor SDK or service API while preserving
these contract boundaries.

## Minimal explicit-endpoint smoke

```python
from reverse_deepagent_browser_provider_hosted_cdp_reference import create_hosted_cdp_reference_browser_provider

provider = create_hosted_cdp_reference_browser_provider(
    browser_url="http://127.0.0.1:9222",
    allocation_mode="explicit-endpoint",
)
session = provider.connect()
provider.stop()
```

## Minimal reference allocation smoke

```python
provider = create_hosted_cdp_reference_browser_provider(
    allocated_browser_url="http://127.0.0.1:9222",
    allocation_mode="in-memory-allocation",
    session_id="reviewed-session-1",
)
session = provider.start()
provider.stop()
```

Do not place raw access tokens, cookies, proxy passwords, or account credentials
in public artifacts. Capability metadata uses booleans and redacted URLs only.
