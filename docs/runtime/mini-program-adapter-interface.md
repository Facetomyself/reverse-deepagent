# Mini-program runtime adapter interface draft

This document sketches the mini-program runtime adapter boundary for future `reverse-deepagent` work. It covers WeChat-style / Alipay-style / similar mini-program environments at the architecture level, without committing to one vendor SDK or developer tool.

Mini-program support must not be treated as normal Web recon. The runtime may use JavaScript, but the execution model, storage APIs, request bridge, native container, package format, and debugging transport differ from a browser page.

## Non-goals for this draft

- Do not require vendor developer tools in public CI.
- Do not launch GUI developer tools, simulators, or account-bound sessions during metadata listing.
- Do not store app ids, session keys, tokens, user identifiers, private packages, or proprietary mini-program code in public fixtures.
- Do not claim pure-Python rebuild readiness for bridge-bound / container-bound sign flows without stable evidence.

## Backend identity

Recommended backend ids and aliases:

| Backend id | Alias examples | Transport examples | Purpose |
| --- | --- | --- | --- |
| `mini-program-devtools` | `mp-devtools`, `wechat-devtools` | `vendor-devtools-cli` | Developer-tool based package inspection, network observation, and runtime evaluation. |
| `mini-program-jscore` | `mp-jscore`, `jscore-bridge` | `js-engine`, `container-bridge` | JSCore / embedded runtime execution or bridge-assisted validation. |
| `mini-program-static` | `mp-static`, `wxapkg-static` | `filesystem` | Offline package / source / config metadata extraction. |

The registry should expose these capabilities without starting vendor tools. Real runtime setup belongs behind explicit runtime construction and local environment checks.

## Capability metadata

Example capability payload:

```json
{
  "backend_id": "mini-program-devtools",
  "display_name": "Mini-program developer tools runtime",
  "transport": "vendor-devtools-cli",
  "target_platforms": ["mini-program"],
  "supports_browser_session": false,
  "supports_web_recon": false,
  "supports_protection_patch": true,
  "supports_artifact_export": true,
  "supports_runtime_context": true,
  "supports_replay_validation": true,
  "managed_chrome": false,
  "mcp_backed": false,
  "evidence_kinds": ["static", "dynamic", "network", "storage", "hook", "note"],
  "artifact_kinds": ["json", "markdown", "source", "trace", "package-metadata"],
  "config": {
    "vendor": "wechat|alipay|unknown",
    "project_path": "optional local path",
    "requires_gui_tool": true,
    "requires_account_session": "depends-on-target"
  }
}
```

`supports_browser_session=false` prevents the coordinator from assuming normal DOM pages, Chrome cookies, localStorage, or fetch/XHR semantics.

## Configuration object

Future implementation should collect vendor/tooling settings in a serializable config object, for example:

```python
@dataclass(frozen=True, slots=True)
class MiniProgramRuntimeConfig:
    backend_id: str = "mini-program-devtools"
    transport: str = "vendor-devtools-cli"
    vendor: str = "wechat"
    devtools_command: str | None = None
    project_path: str | None = None
    app_id: str | None = None
    request_timeout: float = 30.0
    startup_timeout: float = 45.0
    artifact_sample_limit: int = 50
```

Exported config summaries must redact `app_id` when it is target-sensitive and must never include account sessions or private keys.

## Runtime context model

Suggested normalized context keys:

| Key | Meaning | Sensitivity |
| --- | --- | --- |
| `project` | package metadata, app config, route list, vendor | medium |
| `container` | runtime version, base library version, platform, language | medium |
| `storage` | mini-program storage metadata / redacted values | high if values included |
| `request_bridge` | `wx.request` / vendor bridge request metadata | medium / high |
| `native_bridge` | native API calls used by sign flow | high |
| `network` | endpoint map, headers shape, replay candidates | medium / high |
| `crypto` | JS crypto / native bridge crypto usage hints | high if keys included |
| `hooks` | runtime hook timeline for bridge APIs and sign functions | can be high |

Mini-program storage should not be normalized as browser `localStorage`. Use platform-specific keys and only map to generic runtime context when semantics are proven equivalent.

## Evidence normalization

Recommended evidence sources:

- `mini_program_project_summary`
- `mini_program_runtime_context`
- `mini_program_request_bridge_timeline`
- `mini_program_storage_summary`
- `mini_program_static_package_summary`
- `mini_program_replay_validation_result`
- `mini_program_hook_timeline`

Example normalized evidence detail:

```json
{
  "vendor": "wechat",
  "route": "pages/search/index",
  "function_name": "buildSign",
  "bridge_api": "wx.request",
  "request_url_shape": "/api/search",
  "sample_input_shape": {"keyword": "string", "timestamp": "number"},
  "sample_output_shape": {"sign": "string"}
}
```

If the sign flow calls native bridge APIs, evidence should record the bridge method names and argument/return shapes, not raw secrets.

## Artifact manifest expectations

Mini-program artifacts should be indexed in `workspace/backend-artifact-manifest.json` with `target_platforms=["mini-program"]`.

Example categories:

| Category | Examples |
| --- | --- |
| `runtime-context` | redacted container / project / storage context |
| `hook-timeline` | bridge API call timeline, sign function call summaries |
| `static-analysis` | package metadata, route map, source inventory, config summary |
| `network` | request bridge metadata, endpoint map, replay candidate info |
| `rebuild` | pure / context-aware / runtime-assisted delivery plan |
| `triage` | native-bridge secret / account-bound session / packed package blockers |

Private packages and unpacked source trees should usually be referenced by local path and hash only, not committed.

## Rebuild delivery semantics

Mini-program sign flows should use the same delivery buckets:

1. **Pure rebuild**: JS algorithm is complete and portable to Python.
2. **Context-aware rebuild**: portable algorithm plus modeled stable platform context.
3. **Runtime-assisted replay**: invoke original mini-program JS / bridge flow under developer tools or a controlled JS runtime.
4. **Triage-only**: native bridge secret, account-bound session, vendor API, packed code, or missing package evidence blocks trustworthy delivery.

Do not confuse “it is JavaScript” with “it is browser JavaScript”. `wx.request` / storage / login / native crypto bridges can make a flow runtime-bound even when the visible code looks small.

## Coordinator integration rules

- Coordinator code must not call vendor devtools, JSCore, or unpackers directly.
- Capability metadata must be discoverable without starting GUI tools.
- Runtime evidence must be normalized into `EvidenceItem` objects.
- Artifacts must flow through `RuntimeArtifactManifest` with `target_platforms=["mini-program"]`.
- Generated delivery risks must be represented as `review_hints`.
- Mini-program adapters should implement platform-neutral `ReverseRuntime` and expose project/container operations through mini-program-specific capability layers. Do not implement `WebReverseRuntime` or overload `ensure_browser_session()` to mean “open mini-program project”.

## Minimal implementation checklist

A future mini-program adapter PR should include:

1. `MiniProgramRuntimeConfig` or equivalent serializable config.
2. Side-effect-free capability metadata tests.
3. Registry registration with aliases.
4. Runtime-unavailable errors for missing devtools / project path / account session.
5. Redacted artifact manifest examples.
6. Documentation for supported vendors and required local tooling.
7. Manual/self-hosted smoke workflow for real developer-tool validation.
