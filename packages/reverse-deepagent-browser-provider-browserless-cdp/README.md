# reverse-deepagent-browser-provider-browserless-cdp

Browserless hosted CDP BrowserProvider plugin package for `reverse-deepagent`.

This is a real provider package seam for Browserless-style hosted Chromium CDP
endpoints. It does not bundle a Browserless SDK and does not allocate sessions
during provider registration or metadata matrix listing. A reviewer must pass an
existing HTTP DevTools endpoint or direct browser WebSocket endpoint explicitly
when creating the provider or running a smoke test.

## Entry point

```toml
[project.entry-points."reverse_deepagent.browser_providers"]
browserless-cdp = "reverse_deepagent_browser_provider_browserless_cdp:browser_provider_registration"
```

Registration and metadata listing are side-effect-free: they do not call the
provider factory, open sockets, probe Browserless, launch browsers, allocate
sessions, read credentials, or call legacy MCP.

## Supported endpoint modes

- `browser_url` / `cdp_browser_url`: an HTTP DevTools browser endpoint compatible
  with `/json/version`, `/json/list`, and `/json/new`. This mode delegates to the
  core `RemoteCDPProvider`.
- `browser_ws_url` / `cdp_browser_ws_url`: a direct browser-level CDP WebSocket
  endpoint, such as a reviewed Browserless `wss://...` URL. This mode uses a
  minimal Target / Runtime / Page CDP session wrapper.

## Minimal smoke with an HTTP DevTools endpoint

```python
from reverse_deepagent_browser_provider_browserless_cdp import create_browserless_cdp_browser_provider

provider = create_browserless_cdp_browser_provider(
    browser_url="http://127.0.0.1:9222",
    browser_navigation_wait=0,
)
session = provider.connect()
provider.stop()
```

## Minimal smoke with a direct WebSocket endpoint

```python
provider = create_browserless_cdp_browser_provider(
    browser_ws_url="wss://production.example.browserless.io?session=<redacted>",
    browser_navigation_wait=0,
)
session = provider.connect()
page = session.new_page("https://example.com")
provider.stop()
```

Do not place raw access tokens, cookies, proxy passwords, or account credentials
in public artifacts. Capability metadata redacts URL query strings and exposes
only boolean endpoint / access-material flags.
