# Runtime adapter pluginization contract

This document defines the runtime adapter contract used by `reverse-deepagent` as the project moves from a Web / JS demo toward swappable runtime backends.

The short version: the DeepAgents coordinator should depend on stable runtime schemas, not raw MCP tools, Chrome details, Playwright details, or future mobile tooling details.

## Current layers

```text
DeepAgents coordinator / subagents
  -> ReverseRuntime interface
    -> Runtime backend registry
      -> backend adapter implementation
        -> concrete transport: mock, MCP stdio, CLI, CDP, Playwright, mobile tooling, ...
```

Current default backends:

| Backend id | Alias | Transport | Purpose |
| --- | --- | --- | --- |
| `mock` | `in-process` | `in-process` | Deterministic public CI and local demo backend. |
| `mcp` | `jsreverser-mcp` | `mcp-stdio` | Real JSReverser MCP + Chrome DevTools backend. |

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

Non-goals:

- The registry should not parse raw MCP return shapes.
- The registry should not start Chrome or launch external tools during metadata listing.
- The registry should not contain target-specific reverse logic.

## Backend configuration objects

Backend-specific configuration should be collected into serializable config objects instead of being scattered across coordinator code.

Current example:

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

Future backend examples:

- `PlaywrightCliConfig`
- `ChromeCdpConfig`
- `AndroidAdbConfig`
- `AndroidFridaConfig`
- `IosFridaConfig`
- `MiniProgramCliConfig`

The Android planning boundary is documented in [`android-adapter-interface.md`](android-adapter-interface.md), the iOS boundary is documented in [`ios-adapter-interface.md`](ios-adapter-interface.md), and the mini-program boundary is documented in [`mini-program-adapter-interface.md`](mini-program-adapter-interface.md). They deliberately treat app/process/container instrumentation as separate runtime shapes instead of overloading Web browser session semantics.

Web-only assumptions are isolated in [`web-runtime-assumptions.md`](web-runtime-assumptions.md). New platform adapters should treat that document as a list of assumptions to avoid inheriting unless they explicitly implement a Web backend.

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
4. Register the backend in `RuntimeBackendRegistry` with aliases.
5. Add tests for metadata listing without starting external processes.
6. Add tests for backend construction.
7. Add or update docs and smoke commands.
8. Ensure generated artifacts are included in `workspace/backend-artifact-manifest.json`.

## Current limitations

- `run_reverse_pipeline(...)` is still the Web-specific orchestrator; platform-neutral pipelines are not implemented yet.
- `ReverseRuntime` intentionally does not expose mobile-specific operations yet; future adapters should add separate capability layers rather than reusing browser method names.
- The registry is in-process Python registration, not package entry-point plugin loading.
- Real MCP smoke still requires a self-hosted runner with Chrome and JSReverser MCP installed.
