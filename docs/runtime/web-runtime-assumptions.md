# Web-specific runtime assumptions

This document isolates assumptions that are intentionally Web-only in the current `reverse-deepagent` demo. Future Android, iOS, and mini-program adapters should not inherit these names or behaviors by accident.

## Why this exists

The current public demo is Web / JS first. That is fine, but Web convenience can quietly turn into architecture debt:

- `ensure_browser_session()` now lives on `WebReverseRuntime` and means browser / DevTools readiness only.
- Chrome debug ports are useful for Web, irrelevant for Android Frida or iOS simulator flows.
- `document.cookie`, `localStorage`, `navigator`, and replay URL derivation are browser concepts.
- JSReverser MCP is a concrete Web runtime backend, not the platform abstraction itself.

The rule: keep Web assumptions inside Web runtime docs, adapters, and paths. Platform adapters should expose their own runtime concepts through stable schemas.

## Current Web-only assumptions

| Assumption | Current location / behavior | Why it is Web-only | Future adapter guidance |
| --- | --- | --- | --- |
| Browser session | `WebReverseRuntime.ensure_browser_session()` returns `BrowserSessionInfo` with page count, page index, active URL. | Android / iOS app processes and mini-program projects are not browser tabs. | Keep non-Web adapters on `ReverseRuntime`; add platform-specific routes instead of overloading browser session. |
| Chrome debug port | Managed Chrome scripts start/stop a DevTools endpoint for MCP recon. | Mobile and mini-program tooling may use ADB, Frida, simctl, vendor devtools, or JSCore. | Keep transport details in backend config and `producer_transport`. |
| JSReverser MCP | `mcp` backend normalizes JSReverser MCP tool output. | It is a Web / DevTools-oriented backend. | Other platforms may use CLI, Frida, static analysis, or vendor tool adapters. |
| DOM / page navigation | Web recon can navigate URLs and inspect pages/scripts. | Native apps and mini-programs use package routes, activities, view controllers, or container pages. | Normalize platform-specific entrypoints as evidence, not fake URLs. |
| Web storage | Runtime context detects `document.cookie`, `localStorage`, `sessionStorage`, `navigator`, timezone, canvas. | Android SharedPreferences, iOS keychain / NSUserDefaults, and mini-program storage are not browser storage. | Use platform-specific context keys and redact sensitive values. |
| Network request derivation | Rebuild derives replay URL from target URL / related `/api/` request. | Mobile and mini-program requests may go through native or vendor request bridges. | Emit `network` / `request_bridge` evidence and runtime-assisted plans when needed. |
| Python replay demo | Current `replay_demo.py` uses `urllib` against an HTTP endpoint. | Native flows may require app process hooks or bridge invocation. | Use pure/context-aware/runtime-assisted delivery buckets instead of forcing HTTP replay. |
| Source context shape | Web source snippets are script URLs, script IDs, line numbers, and function candidates. | APK/IPA/package sources may be dex, Mach-O, Swift symbols, unpacked mini-program modules. | Keep source evidence normalized but platform-aware. |

## Web runtime boundary

Current Web runtime responsibilities:

1. Ensure browser / DevTools session readiness.
2. Navigate or select a target page.
3. Collect network requests, script hits, request initiators, source snippets, storage, and runtime context.
4. Apply minimal anti-debug / anti-clear / redirect protection when needed.
5. Validate JS sign candidates in the browser runtime.
6. Export Web session artifacts.
7. Feed rebuild delivery with source context, sample inputs/outputs, replay URL, and runtime context.

These responsibilities belong to Web backends such as:

- `mock` for deterministic public CI.
- `mcp` / `jsreverser-mcp` for real JSReverser MCP + Chrome DevTools.
- `playwright-cli` for side-effect-light Playwright CLI probes plus static source fetch.
- `chrome-cdp` for existing Chrome DevTools endpoint probes without launching Chrome.
- `browser-cli` for generic local browser CLI shims.

They should not be treated as requirements for `android-*`, `ios-*`, or `mini-program-*` backends.

## Naming guidance

Avoid these mistakes:

- Do not call an Android app process a “browser session”.
- Do not call mini-program storage `localStorage` unless the vendor API truly behaves that way and the adapter documents the mapping.
- Do not put ADB / Frida / simctl / vendor devtools commands in coordinator code.
- Do not represent a native method hook as a fake script URL.
- Do not mark a bridge-bound or device-bound flow as pure replay just because a single runtime validation returned a sign.

Prefer these patterns:

- `RuntimeBackendCapabilities.target_platforms` to separate `web`, `android`, `ios`, and `mini-program`.
- `producer_transport` for `mcp-stdio`, `frida-adb`, `frida-usb`, `vendor-devtools-cli`, and similar details.
- `RuntimeArtifactManifest` entries with platform-neutral categories.
- `EvidenceItem.source` names that preserve platform meaning, such as `android_method_hook_timeline` or `mini_program_request_bridge_timeline`.
- `review_hints` to block misleading pure delivery.

## Coordinator contract

The coordinator may depend on these stable concepts:

- `TaskCard`
- `RouterResult`
- `ReconResult`
- `FinalResult`
- `RuntimeBackendCapabilities`
- `RuntimeArtifactManifest`
- `EvidenceItem`
- `ArtifactRef`
- Rebuild delivery buckets: pure, context-aware, runtime-assisted, triage-only

The coordinator must not depend directly on:

- raw MCP tool names,
- Chrome debug port defaults,
- browser page index semantics,
- DOM APIs,
- browser storage names for non-Web platforms,
- ADB / Frida / simctl / vendor devtools commands,
- raw platform logs that have not been normalized.

## How future adapters should plug in

A future non-Web adapter should start with:

1. capability metadata,
2. serializable config object,
3. side-effect-free registry registration,
4. normalized evidence source names,
5. platform-neutral artifact manifest categories,
6. runtime-unavailable error path,
7. docs and self-hosted/manual smoke instructions.

Only after that should it add real device/tool invocation.

## Compatibility promise

Existing Web outputs stay compatible:

- `workspace/task-card.json`
- `workspace/route-decision.json`
- `workspace/recon-result.json`
- `workspace/final-result.json`
- `workspace/rebuild-plan.json`
- `workspace/backend-artifact-manifest.json`
- `rebuild/sign_rebuild.py`
- `rebuild/replay_demo.py`
- `rebuild/scrapy_middleware.py`
- `exports/artifact-index.json`

The point is not to rename the working Web pipeline. The point is to keep it from leaking into every future platform. 这活儿要是不现在切清楚，后面每加一个平台都得背一身 Web 包袱，纯纯给自己挖坑。
