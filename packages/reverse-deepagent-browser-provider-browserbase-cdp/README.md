# reverse-deepagent-browser-provider-browserbase-cdp

Browserbase CDP BrowserProvider plugin package for `reverse-deepagent`.

This package is a real third-party hosted CDP provider baseline, not a template:

- declares the `reverse_deepagent.browser_providers` entry point `browserbase-cdp`;
- keeps registration, metadata listing, doctor matrix, and production-readiness evaluation side-effect free;
- does not read `BROWSERBASE_API_KEY`, create sessions, open sockets, or invoke provider factories during metadata paths;
- can attach to a reviewed Browserbase `connectUrl` / browser WebSocket endpoint;
- can explicitly create a Browserbase Session with `POST /v1/sessions` only when `start()` is called on an explicitly created provider;
- redacts API URLs, connect URLs, session IDs, and project IDs in exported metadata and event logs.

## Install

From this repository checkout:

```bash
uv pip install --python "<repo-root>/.venv/bin/python" -e "<repo-root>/packages/reverse-deepagent-browser-provider-browserbase-cdp"
```

For direct CDP WebSocket support, ensure the core optional CDP dependency is installed:

```bash
uv pip install --python "<repo-root>/.venv/bin/python" -e "<repo-root>[cdp]"
```

## Configuration

The provider accepts explicit keyword arguments through `BrowserProviderRegistry.create(...)`:

- `connect_url` / `browser_ws_url` / `browserbase_connect_url`: reviewed Browserbase CDP WebSocket URL;
- `api_key`: Browserbase API key, used only by explicit `start()` session creation;
- `project_id`: Browserbase project id;
- `api_base_url`: API base URL, defaulting to `https://api.browserbase.com`;
- `keep_alive`, `session_timeout_seconds`, `region`: optional session creation settings;
- `browser_navigation_wait`, `browser_connect_timeout`: local BrowserProvider timing knobs.

The factory also honors `BROWSERBASE_CONNECT_URL`, `BROWSERBASE_API_KEY`, `BROWSERBASE_PROJECT_ID`, and `BROWSERBASE_API_BASE_URL`, but only after explicit provider creation. Metadata listing never reads them.

## Side-effect boundary

- `browser_provider_registration()` is metadata-only.
- `describe()` returns redacted config and production-readiness metadata.
- `is_available()` is local config inspection only; it does not probe Browserbase.
- `connect()` attaches only to a caller-supplied reviewed connect URL.
- `start()` is the only path that can call Browserbase Session creation.
- `stop()` only closes local CDP state; it does not attempt account-level cleanup.

Use `reverse-agent-browser-provider-smoke --launch-browser-smoke` only when you explicitly want to create/connect a real session and write reviewed smoke evidence.
