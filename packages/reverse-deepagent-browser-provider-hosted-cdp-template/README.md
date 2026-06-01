# reverse-deepagent-browser-provider-hosted-cdp-template

Hosted CDP BrowserProvider plugin template for `reverse-deepagent`.

Use this package when integrating a hosted browser service, anti-detect browser
SaaS, enterprise browser pool, or remote CDP broker. It is intentionally an
external package so the coordinator and `native-web` runtime stay provider
neutral.

## Entry point

```toml
[project.entry-points."reverse_deepagent.browser_providers"]
hosted-cdp-template = "reverse_deepagent_browser_provider_hosted_cdp_template:browser_provider_registration"
```

`browser_provider_registration()` returns non-secret `BrowserProviderCapabilities`
and a delayed factory. Registry metadata listing and doctor matrix output must
not call the factory, probe the hosted service, open sockets, import vendor SDKs,
launch browsers, or call MCP.

## Runtime behavior

- Metadata-only paths classify the provider as `review-required`, not production
  complete.
- `connect()` / `start()` require an explicit `browser_url` / `cdp_browser_url`.
- When a CDP browser URL is provided, the template delegates to the core
  `RemoteCDPProvider` session adapter so integrators can smoke the BrowserProvider
  contract before replacing the connection code with a vendor SDK.
- When no endpoint is configured, lifecycle methods raise
  `BrowserProviderUnavailableError` with setup guidance.

## Replace for production

- Change `HOSTED_CDP_BROWSER_PROVIDER_ID` and aliases.
- Replace `HostedCDPBrowserProviderConfig` with your non-secret vendor config.
- Keep raw access material outside capability metadata; report only booleans,
  redacted URLs, digests, or policy labels.
- Replace `_delegate()` if the vendor does not expose a standard Chrome DevTools
  endpoint directly.
- Keep `production_readiness` honest: document health checks, profile ownership,
  proxy ownership, extension behavior, humanize support, session recovery, and
  side-effect boundaries before marking a real provider production-ready.

This template is a production seam scaffold, not a bundled vendor integration.
It does not ship vendor SDKs, manage accounts, allocate hosted browser sessions,
or validate proxy / geoip behavior.
