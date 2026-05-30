# Plan: BrowserProvider Native Runtime and MCP Deprecation

## Plan Task Card

- task_description: Move `reverse-deepagent` away from `jsreverser-mcp` as the core Web runtime and introduce a pluggable BrowserProvider architecture. Prioritize native browser instrumentation and support CloakBrowser as a replaceable provider.
- mode: planning
- plan_target: BrowserProvider architecture, native Web runtime, MCP legacy migration.
- constraints:
  - Do not remove existing MCP functionality until native parity is sufficient.
  - Keep current artifact schemas backward compatible.
  - Keep browser-specific details below Web runtime boundaries.
  - Keep CloakBrowser optional due binary/license/platform constraints.
  - Do not let DeepAgents coordinator depend on raw browser, CDP, Playwright, or MCP tool details.
- execution_flags:
  - staged migration
  - test each backend independently
  - preserve legacy commands until replacement is validated

## Planning artifacts

- Public migration plan: `docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md`.
- Execution-ready do-plan entry: `.codex/plans/browser-provider-mcp-deprecation-plan.md`.
- Runtime architecture: `docs/runtime/browser-provider-architecture.md`.
- CloakBrowser provider notes: `docs/runtime/cloakbrowser-provider.md`.

## Current state

The project already has useful pieces:

- `WebReverseRuntime` / `ReverseRuntime` contracts.
- `RuntimeBackendRegistry` for backend registration.
- `JSReverserRuntime` backed by `jsreverser-mcp`.
- Lightweight Web backends for `playwright-cli`, `chrome-cdp`, and `browser-cli`.
- Managed Chrome debug launcher and lifecycle tests.
- `reverse-agent-doctor` for browser / MCP readiness checks.
- Artifact manifest and stable JSON report outputs.

The gap is that MCP still acts as the richest Web runtime. The browser is not yet a first-class replaceable module, and native collectors do not exist as project-owned components.

## Target state

```text
DeepAgents coordinator
  -> WebReverseRuntime
    -> NativeWebRuntime
      -> BrowserProvider
      -> CollectorRegistry
      -> HookManager
      -> ArtifactExporter
    -> LegacyMcpRuntime
```

Default long-term flow:

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --task-text "https://example.com 找 sign 入口"
```

Current compatibility flow:

```bash
reverse-agent-demo \
  --runtime legacy-mcp \
  --ensure-chrome
```

`legacy-mcp` is the explicit backend id; `mcp` and `jsreverser-mcp` remain runnable compatibility aliases for the transition window.

## Milestones

### Phase 1: BrowserProvider contract

Status: implemented in the initial contract layer.

Deliverables:

- `src/reverse_deepagent/browser/base.py`
- `src/reverse_deepagent/browser/capabilities.py`
- `src/reverse_deepagent/browser/registry.py`
- `tests/test_browser_provider_contract.py`
- `tests/test_browser_provider_registry.py`

Acceptance:

- Providers can register side-effect-free metadata.
- Unknown provider errors are explicit.
- Capability metadata is JSON-serializable and contains no secrets.
- No browser process is launched by metadata listing.

Current evidence:

- `BrowserProviderCapabilities` is serializable through `model_dump(mode="json")`.
- `BrowserProviderRegistry.list_metadata()` returns capability metadata without invoking provider factories.
- Secret-like capability metadata keys are rejected at registration time.
- Unit tests: `tests.test_browser_provider_contract`, `tests.test_browser_provider_registry`.

### Phase 2: Playwright-compatible session layer

Status: contract and provider skeleton implemented; real browser smoke pending optional Playwright installation and browser binary availability.

Deliverables:

- `src/reverse_deepagent/browser/session.py`
- `src/reverse_deepagent/browser/providers/playwright_chromium.py`
- basic page/session abstraction tests.

Acceptance:

- Can launch or connect a Playwright Chromium session.
- Can open a URL, read title/content, evaluate JS, and close cleanly.
- Can produce a normalized `BrowserSessionInfo` equivalent.
- No MCP process is started.

Current evidence:

- `PlaywrightBrowserSessionAdapter` and `PlaywrightBrowserPageAdapter` wrap Playwright-compatible objects.
- `PlaywrightChromiumProvider` exposes serializable capabilities and structured unavailable errors when `playwright` is missing.
- Optional dependency group: `.[browser]` installs `playwright` but does not force browser binary download in default installs.
- Unit tests: `tests.test_playwright_session`, `tests.test_playwright_provider`.

Remaining validation:

- Install `.[browser]` in an environment allowed to download/use Playwright browsers.
- Run a headed/headless smoke that opens a URL, captures title/content/screenshot, and closes without residual browser processes.

### Phase 3: Native collector baseline

Status: provider-neutral baseline implemented; CDP-enhanced depth remains Phase 8.

Deliverables:

- `collectors/dom.py`
- `collectors/storage.py`
- `collectors/console.py`
- `collectors/network.py`
- `collectors/scripts.py`
- `collectors/screenshots.py`

Acceptance:

- `NetworkCollector` emits normalized request samples.
- `ScriptCollector` emits script inventory and keyword source hits.
- `StorageCollector` emits cookies/localStorage/sessionStorage with safe redaction points.
- `ConsoleCollector` emits logs/warnings/errors.
- Collectors work with Playwright-compatible pages and do not know whether the provider is CloakBrowser or Chromium.

Current evidence:

- `src/reverse_deepagent/browser/collectors/` contains DOM, storage, console, network, script, and screenshot collectors.
- Collectors consume `BrowserPage` / Playwright-compatible adapters rather than MCP tools.
- Unit tests: `tests.test_browser_collectors`.

Remaining validation:

- Wire collectors into `NativeWebRuntime` and verify artifact compatibility.
- Add CDP-enhanced request initiator, response body, script source, and WebSocket frame support in Phase 8.

### Phase 4: NativeWebRuntime

Status: minimal runtime implemented and registered; advanced provider options and real browser smoke remain pending.

Deliverables:

- `src/reverse_deepagent/adapters/native_web.py`
- runtime registry entry: `native-web` with aliases `web`, `browser-native`.
- CLI flags:
  - `--browser`
  - `--browser-profile-dir`
  - `--browser-headless`
  - `--browser-humanize`
  - `--browser-proxy`
  - `--browser-locale`
  - `--browser-timezone`

Acceptance:

- `reverse-agent-demo --runtime native-web --browser playwright-chromium` produces `ReconResult` and current artifact files.
- `backend-artifact-manifest.json` marks producer backend as `native-web` and provider as metadata.
- Existing mock and MCP tests remain green.

Current evidence:

- `native-web` is registered with aliases `web` and `browser-native`.
- `NativeWebRuntime` can run with a fake BrowserProvider and write current core artifacts without MCP.
- CLI now accepts `--browser`, `--browser-profile-dir`, `--browser-headless`, `--browser-executable-path`, and `--browser-args`.
- Unit tests: `tests.test_native_web_runtime`.

Remaining validation:

- Add `--browser-humanize`, `--browser-proxy`, `--browser-locale`, and `--browser-timezone` once CloakBrowser/provider configs need them.
- Run real `reverse-agent-demo --runtime native-web --browser playwright-chromium` after installing `.[browser]` and a Playwright browser binary.
- Ensure backend manifest carries provider metadata in downstream artifact entries.

### Phase 5: CloakBrowser provider

Status: provider skeleton, optional dependency, and browser-provider doctor metadata checks added; real CloakBrowser binary smoke remains pending.

Deliverables:

- optional dependency group:
  - `cloak = ["cloakbrowser>=...,<..."]`
- `src/reverse_deepagent/browser/providers/cloakbrowser.py`
- `docs/runtime/cloakbrowser-provider.md`
- execution plan entry: `.codex/plans/browser-provider-mcp-deprecation-plan.md`
- doctor support: `reverse-agent-doctor --browser cloakbrowser`

Acceptance:

- Missing dependency produces structured guidance, not import traceback.
- Installed provider can launch a persistent context.
- Provider reports stealth/humanize/persistent profile capabilities.
- Basic native collectors work through the same Playwright-compatible session layer.
- CloakBrowser binary is not committed or redistributed by this repo.

Current evidence:

- Optional dependency group `.[cloak]` is declared without affecting default installs.
- `CloakBrowserProvider` reports stealth/humanize/persistent profile capabilities.
- Proxy configuration is redacted from capability metadata.
- Missing dependency raises `BrowserProviderUnavailableError` with install guidance.
- `native-web` factory can select `--browser cloakbrowser` without importing or launching CloakBrowser during metadata listing.
- Unit tests: `tests.test_cloakbrowser_provider`.

Remaining validation:

- Install `.[cloak]` in an environment allowed to download/use CloakBrowser binaries.
- Run persistent-context smoke against a safe local page.
- BrowserProvider doctor support is implemented for metadata/dependency checks; keep real launch smoke optional.
- Keep `docs/runtime/cloakbrowser-provider.md` updated after real binary smoke.

### Phase 6: BrowserProvider doctor mode

Status: metadata/dependency checks implemented; related tests and CLI redaction smoke pass locally.

Deliverables:

- `reverse-agent-doctor --browser playwright-chromium`
- `reverse-agent-doctor --browser cloakbrowser`
- `--launch-browser-smoke` explicit launch gate

Acceptance:

- BrowserProvider doctor does not require MCP or Chrome static checks in browser-only mode.
- Missing optional dependencies produce structured guidance.
- Provider metadata is collected without browser launch.
- Proxy configuration is redacted from doctor output.

### Phase 7: Native artifact parity

Status: native DOM, console, script inventory, and navigation evidence are mapped to workspace artifacts; related tests pass locally.

Deliverables:

- `workspace/dom-snapshot.json`
- `workspace/console-messages.json`
- `workspace/script-inventory.json`
- `workspace/navigation-events.json`
- backend manifest metadata containing `browser_provider` and `browser_provider_transport` when available

Acceptance:

- Native Web fake-provider pipeline writes the new workspace artifacts.
- Existing legacy MCP artifact mappings remain unchanged.
- Manifest entries expose provider metadata without secrets.

### Phase 8: CDP-enhanced collectors

Status: CDP event cache and metadata collector implemented and tested locally; script source fallback now uses the provider-neutral script inventory, and WebSocket frame fallback can consume runtime hook timeline events when CDP frame events are unavailable. Real browser smoke remains pending.

Deliverables:

- CDP session helper.
- request initiator capture.
- response body metadata capture.
- `Debugger.scriptParsed` script cache support.
- WebSocket frame capture.
- HTML script-inventory fallback for source metadata when `Debugger.scriptParsed` events are unavailable.
- runtime hook timeline fallback for WebSocket frame metadata when CDP frame events are unavailable.

Acceptance:

- Native runtime can produce `request-initiators.json` without MCP when provider supports CDP.
- Native runtime can produce `source-contexts.json` from cached script sources.
- WebSocket metadata is captured when available.
- Missing CDP event cache no longer means immediate placeholder output for script sources or hook-observed WebSocket frames.
- Providers without CDP degrade with explicit `unsupported` evidence rather than failing the run.

### Phase 9: Hook and breakpoint migration

Status: hook baseline, WebSocket send/message capture, and provider-neutral BreakpointManager baseline are implemented and tested locally; real browser breakpoint smoke remains pending.

Deliverables:

- `hooks/fetch_xhr.py`
- `hooks/cookie.py`
- `hooks/anti_debug.py`
- `hooks/breakpoints.py`
- WebSocket send/message hook capture through the shared hook timeline.
- `virtual://workspace/breakpoints.json` protection artifact ref / evidence mapping
- runtime-observe playbook integration.

Acceptance:

- Fetch/XHR hook can capture request parameters before app encryption/signing wrappers send them.
- Anti-debug patches are minimal and auditable.
- Breakpoint features are behind provider capability checks and only run for explicit protection/debug requests.
- Hook output is emitted as normalized evidence and artifact files.

### Phase 10: MCP legacy downgrade

Status: implemented locally. `legacy-mcp` is the canonical backend id; `mcp` and `jsreverser-mcp` remain compatibility aliases. Doctor now supports `--legacy-mcp`, and native-web remains the README quickstart recommendation.

Deliverables:

- Rename docs wording from `mcp` preferred path to `legacy-mcp` compatibility path.
- Keep CLI alias `mcp` temporarily for backward compatibility.
- Update doctor:
  - default checks native browser provider.
  - `--legacy-mcp` checks jsreverser-mcp.
- Move MCP smoke docs under legacy runtime section.

Acceptance:

- README quickstart uses `native-web`.
- MCP smoke remains runnable for users who still need it.
- Public CI does not require MCP.
- Native Web runtime is the default recommendation.

## Test strategy

- Unit tests for provider registry and metadata.
- Fake provider tests for collectors.
- Playwright provider smoke tests gated by local availability.
- CloakBrowser smoke tests optional and skipped when dependency/binary is unavailable.
- Legacy MCP tests retained until native collectors reach parity.
- Artifact compatibility tests compare native runtime output keys with legacy MCP output keys.

## Compatibility rules

- Do not rename current artifact keys unless a migration shim exists.
- Do not make CloakBrowser a hard dependency.
- Do not remove `mcp` alias until at least one release after `legacy-mcp` is documented.
- Do not expose raw cookies, API keys, tokens, or private headers in provider capability metadata.

## Definition of done

The MCP deprecation path is complete when:

1. `reverse-agent-demo --runtime native-web --browser playwright-chromium` works without MCP.
2. `reverse-agent-demo --runtime native-web --browser cloakbrowser` works when optional dependency is installed.
3. Native runtime emits current core artifacts.
4. Basic request/source/storage/console/DOM evidence no longer depends on MCP.
5. MCP docs are explicitly legacy.
6. `reverse-agent-doctor` can diagnose browser providers independently from MCP.
7. MCP can be removed from a clean environment without breaking the native Web quickstart.
