# Runtime adapter pluginization contract

This document defines the runtime adapter contract used by `reverse-deepagent` as the project moves from a Web / JS demo toward swappable runtime backends.

The short version: the DeepAgents coordinator should depend on stable runtime schemas, not raw MCP tools, Chrome details, Playwright details, or future mobile tooling details.

## Current layers

```text
DeepAgents coordinator / subagents
  -> ReverseRuntime interface
    -> Runtime backend registry
      -> native Web runtime
        -> BrowserProvider registry
        -> native collectors / hooks / artifact exporters
      -> legacy backend adapters
        -> MCP stdio, CLI, CDP, mobile tooling, ...
```

Backend direction:

| Backend id | Alias | Transport | Purpose |
| --- | --- | --- | --- |
| `mock` | `in-process` | `in-process` | Deterministic public CI and local demo backend. |
| `native-web` | `web`, `browser-native` | `browser-provider` | Target Web runtime with project-owned collectors and replaceable browser providers. |
| `legacy-mcp` | `mcp`, `jsreverser-mcp` | `mcp-stdio` | Compatibility backend for JSReverser MCP + Chrome DevTools while native parity is built. |

The backend registry is exposed through:

```python
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends

print(list_runtime_backends())
runtime = build_runtime("mock")
```

## Required runtime interface

A backend must implement the platform-neutral `ReverseRuntime` base contract:

```python
class ReverseRuntime(ABC):
    def describe_capabilities(self) -> RuntimeBackendCapabilities: ...
    def apply_minimal_protection(self, protection_name: str, context: dict | None = None) -> ProtectionResult: ...
    def export_reverse_artifacts(self, final_result: FinalResult | None = None) -> RuntimeExportBundle: ...
```

Web/browser backends additionally implement `WebReverseRuntime`:

```python
class WebReverseRuntime(ReverseRuntime):
    def ensure_browser_session(self) -> BrowserSessionInfo: ...
    def run_web_recon(self, task_card: TaskCard, route_result: RouterResult) -> ReconResult: ...
```

`run_reverse_pipeline(...)` is the Web pipeline entrypoint and rejects non-`WebReverseRuntime` adapters. Android, iOS, and mini-program backends should not overload `ensure_browser_session()` to mean “attach app process” or “open project”; they should stay on `ReverseRuntime` and expose platform-specific orchestration through separate capability layers.

## Capability metadata

Every backend should expose `RuntimeBackendCapabilities` through `describe_capabilities()`.

Important fields:

- `backend_id`: stable backend id, for example `mock` or `mcp`.
- `display_name`: human-readable backend name.
- `transport`: implementation transport, for example `in-process`, `mcp-stdio`, `cdp`, `playwright-cli`, `adb`, `frida`, or `mini-program-cli`.
- `target_platforms`: target platform list, currently usually `web`.
- `supports_browser_session`: can inspect / manage browser session state.
- `supports_web_recon`: can run the current Web recon flow.
- `supports_protection_patch`: can apply minimal anti-debug / environment patches.
- `supports_artifact_export`: can export runtime/session artifacts.
- `supports_runtime_context`: can collect storage / environment / device context.
- `supports_replay_validation`: can validate candidate sign functions at runtime.
- `managed_chrome`: can be paired with the managed Chrome launcher.
- `mcp_backed`: uses MCP transport under the hood.
- `evidence_kinds`: common evidence categories the backend emits.
- `artifact_kinds`: common artifact categories the backend emits.
- `config`: non-secret runtime configuration summary.

Capability metadata is a routing and inspection contract. It should not contain secrets, cookies, tokens, or target-specific proprietary code.

## Backend registry responsibilities

`RuntimeBackendRegistry` owns backend lookup and construction.

Responsibilities:

1. Register canonical backend ids and aliases.
2. Provide JSON-serializable capability metadata without starting external processes.
3. Construct a backend only when explicitly requested by `build_runtime(...)`.
4. Keep unknown backend failures explicit and actionable.
5. Load optional backend plugins from the `reverse_deepagent.runtime_backends` Python entry-point group without invoking backend factories during metadata listing.

Non-goals:

- The registry should not parse raw MCP return shapes.
- The registry should not start Chrome or launch external tools during metadata listing.
- The registry should not contain target-specific reverse logic.

## Backend configuration objects

Backend-specific configuration should be collected into serializable config objects instead of being scattered across coordinator code.

For native Web runtime, browser-specific configuration belongs to BrowserProvider config objects, not the coordinator. Examples include `PlaywrightChromiumConfig`, `CloakBrowserConfig`, `ChromeCDPConfig`, and `RemoteCDPConfig`.

Legacy MCP example:

```python
from reverse_deepagent.adapters import JSReverserMcpConfig, create_jsreverser_mcp_runtime

config = JSReverserMcpConfig(
    command="/opt/homebrew/bin/jsreverser-mcp",
    browser_url="http://127.0.0.1:9461",
    request_timeout=30.0,
    startup_timeout=15.0,
)
runtime = create_jsreverser_mcp_runtime(config=config)
```

`JSReverserMcpConfig` covers:

- MCP command path
- Chrome DevTools browser URL
- request / startup timeouts
- backend id / display name / transport
- page size and post-navigation wait
- runtime context sample count / sample interval

Implemented lightweight Web backend examples:

- `LightweightWebRuntimeConfig` with `transport=playwright-cli`
- `LightweightWebRuntimeConfig` with `transport=chrome-cdp`
- `LightweightWebRuntimeConfig` with `transport=browser-cli`

Planned native Web examples:

- `NativeWebRuntimeConfig` selecting a BrowserProvider.
- `CloakBrowserConfig` for stealth browser sessions and persistent profiles.
- `PlaywrightChromiumConfig` for the portable baseline provider.
- `RemoteCDPConfig` for browserless, Docker, or remote debug endpoints.

Future platform backend examples:

- `AndroidAdbConfig`
- `AndroidFridaConfig`
- `IosFridaConfig`
- `MiniProgramCliConfig`

The Android planning boundary is documented in [`android-adapter-interface.md`](android-adapter-interface.md), the iOS boundary is documented in [`ios-adapter-interface.md`](ios-adapter-interface.md), and the mini-program boundary is documented in [`mini-program-adapter-interface.md`](mini-program-adapter-interface.md). They deliberately treat app/process/container instrumentation as separate runtime shapes instead of overloading Web browser session semantics.

Web-only assumptions are isolated in [`web-runtime-assumptions.md`](web-runtime-assumptions.md). New platform adapters should treat that document as a list of assumptions to avoid inheriting unless they explicitly implement a Web backend.


## BrowserProvider plug-in boundary

The Web browser itself should be a plug-in below `NativeWebRuntime`.

A provider owns:

1. browser launch/connect/stop,
2. profile and login-state handling,
3. optional CDP or Playwright session access,
4. provider capability metadata,
5. provider-specific errors and setup guidance.

A provider does **not** own:

1. route decisions,
2. evidence scoring,
3. artifact schema design,
4. report generation,
5. target-specific reverse logic.

This keeps `cloakbrowser`, ordinary Playwright Chromium, local Chrome CDP, and remote CDP interchangeable without rewriting the recon pipeline.

The full target architecture is documented in [`browser-provider-architecture.md`](browser-provider-architecture.md).

## Artifact manifest contract

Every pipeline run writes a typed backend artifact manifest:

```text
workspace/backend-artifact-manifest.json
```

The manifest uses:

- `RuntimeArtifactManifest`
- `RuntimeArtifactManifestEntry`

Each entry records:

- `artifact_key`
- `path`
- `category`
- `kind`
- `producer_backend_id`
- `producer_transport`
- `target_platforms`
- `description`
- `metadata`

This file is additive. It does **not** replace:

```text
exports/artifact-index.json
```

Downstream tools should prefer the typed manifest when they need backend-aware artifact routing, and keep using the old artifact index when they need backward compatibility.

The platform-neutral category vocabulary is documented in [`platform-neutral-artifact-categories.md`](platform-neutral-artifact-categories.md). Existing Web categories (`workspace`, `report`, `export`, `rebuild`) remain valid and backward compatible.

## Coordinator boundary rules

The coordinator and subagents should consume these stable objects:

- `TaskCard`
- `RouterResult`
- `ReconResult`
- `FinalResult`
- `RuntimeBackendCapabilities`
- `RuntimeArtifactManifest`
- `EvidenceItem`
- `ArtifactRef`

They should avoid depending on:

- raw MCP tool names,
- raw MCP Markdown / fenced JSON return text,
- Chrome debug port defaults,
- browser-specific storage assumptions outside runtime context capture,
- Playwright / CDP / ADB / Frida command details.

If a backend returns weird raw output, normalize it inside that backend adapter and expose stable evidence / artifacts upward.

## Extension path for non-Web runtimes

Do not force Android, iOS, or mini-program support through Web-only names.

A future mobile backend should first define:

1. backend id and aliases,
2. transport and target platforms,
3. capability metadata,
4. config object,
5. artifact manifest categories,
6. evidence normalization rules.

Example capability sketch:

```json
{
  "backend_id": "android-frida",
  "transport": "frida-adb",
  "target_platforms": ["android"],
  "supports_browser_session": false,
  "supports_web_recon": false,
  "supports_runtime_context": true,
  "supports_artifact_export": true,
  "evidence_kinds": ["dynamic", "hook", "storage", "note"]
}
```

The project can then add Android-specific methods or higher-level workflows without pretending they are Web recon.

## Implementation checklist for a new backend

1. Define a serializable config object.
2. Implement or wrap `ReverseRuntime`; implement `WebReverseRuntime` only for genuine browser/Web backends.
3. Implement `describe_capabilities()`.
4. Register the backend in `RuntimeBackendRegistry` with aliases, or expose a package entry point under `reverse_deepagent.runtime_backends` that returns one or more `RuntimeBackendRegistration` objects.
5. Keep registration side-effect light: entry-point loading may import plugin Python code, but it must not start browsers, MCP processes, device tooling, or network sessions; backend factories run only when explicitly selected.
6. Add tests for metadata listing without starting external processes.
7. Add tests for backend construction.
8. Add or update docs and smoke commands.
9. Ensure generated artifacts are included in `workspace/backend-artifact-manifest.json`.

## Current limitations

- `run_reverse_pipeline(...)` is still the Web-specific orchestrator and intentionally rejects non-`WebReverseRuntime` adapters.
- `run_platform_pipeline(...)` / `reverse-agent-platform` now provide the platform-neutral baseline: task card, route decision, capability capture, runtime export bundle, optional platform tool probe, backend manifest, report, and artifact index. It does not yet perform Android/iOS/mini-program-specific hook, static-analysis, or replay-validation workflows.
- `playwright-cli`, `chrome-cdp`, and `browser-cli` are intentionally lightweight Web backends. They expose Web runtime schemas, but they do not start Chrome, capture live network timelines, or execute page JavaScript validation unless a future transport explicitly implements those operations.
- `ReverseRuntime` intentionally does not expose mobile-specific operations yet; future adapters should add separate capability layers rather than reusing browser method names.
- Runtime backend entry-point loading is implemented as the split seam for optional packages; `packages/reverse-deepagent-legacy-mcp/` owns the optional legacy MCP registration / factory implementation, while `reverse_deepagent.runtime.legacy_mcp` remains a compatibility shim with alias warnings, plugin delegation, and install guidance. Core no longer ships a built-in legacy MCP factory fallback; if the optional package is missing, `legacy-mcp` / `mcp` runtime construction returns structured install guidance instead of starting Chrome or MCP.
- Real MCP smoke still requires a self-hosted runner with Chrome and JSReverser MCP installed.
- `native-web` and BrowserProvider contracts are implemented as selectable Web runtime infrastructure; the CLI default still stays on `mock` for deterministic public CI, and real BrowserProvider smoke remains explicit / environment-gated.
- MCP is retained as a compatibility backend during migration; it is not the long-term Web architecture center.
