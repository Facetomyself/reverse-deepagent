# Platform-neutral runtime artifact categories

This document defines the shared artifact category vocabulary used by `workspace/backend-artifact-manifest.json` as runtime support expands from Web to Android, iOS, and mini-program targets.

The goal is compatibility: existing Web artifacts keep their current categories, while future platform adapters can describe their outputs without inventing one-off names or pretending everything is a browser workspace file.

## Stable category vocabulary

The canonical category tuple is exported as `PLATFORM_NEUTRAL_ARTIFACT_CATEGORIES` from `reverse_deepagent.runtime`.

| Category | Meaning | Platform notes |
| --- | --- | --- |
| `workspace` | Core normalized pipeline state such as task card, route, recon, final result, rebuild plan, or backend manifest. | Existing Web-compatible category. |
| `report` | Human / machine-readable final reports. | Existing Web-compatible category. |
| `export` | Indexes and exported runtime/session bundles. | Existing Web-compatible category. |
| `runtime-context` | Captured environment, storage, device, process, container, or session context. | Web storage / navigator, Android device/process, iOS bundle/process, mini-program container/storage. |
| `hook-timeline` | Ordered hook / call / bridge events. | JS hooks, Frida method calls, native bridge calls, request bridge calls. |
| `static-analysis` | Offline source/package/binary metadata. | JS bundle inventory, APK/dex, IPA/Mach-O, mini-program package metadata. |
| `network` | Request/response metadata, endpoint map, replay candidates. | Browser fetch/XHR, mobile traffic observations, mini-program request bridge. |
| `rebuild` | Generated pure, context-aware, runtime-assisted, or partial rebuild artifacts. | Existing generated Python files remain `rebuild`. |
| `triage` | Explicit unsupported / protected / not-ready analysis. | WASM / VM / native secret / packer / account-bound blockers. |
| `source` | Extracted source snippets, deobfuscated fragments, source maps, or script context. | Use when source evidence is a first-class artifact instead of generic workspace JSON. |
| `trace` | Runtime traces that are not specifically hook timelines. | Performance traces, call stacks, debug timelines. |
| `session` | Runtime session snapshots or replayable session descriptors. | Browser session, Frida session metadata, devtools project session. |
| `other` | Fallback for uncategorized artifacts. | Should be rare; prefer adding a documented category before broad use. |

## Current Web alias compatibility

The current Web demo emits these existing categories and they remain valid:

| Existing category | Canonical meaning | Notes |
| --- | --- | --- |
| `workspace` | `workspace` | No migration needed. |
| `report` | `report` | No migration needed. |
| `export` | `export` | No migration needed. |
| `rebuild` | `rebuild` | No migration needed. |

The compatibility map is exported as `WEB_ARTIFACT_CATEGORY_ALIASES`. It is intentionally boring right now because the current manifest is already using acceptable top-level names.

## `target_platforms` semantics

`target_platforms` belongs to both manifest-level metadata and entry-level metadata.

Recommended values:

- `web`
- `android`
- `ios`
- `mini-program`
- future values should use lowercase kebab-case.

Rules:

1. Manifest-level `target_platforms` describes the backend/run as a whole.
2. Entry-level `target_platforms` describes the artifact producer context.
3. A mixed artifact can list multiple platforms, for example `['web', 'android']` for a shared schema example.
4. Do not encode transport names as platforms. Use `producer_transport` for `mcp-stdio`, `frida-adb`, `vendor-devtools-cli`, and similar details.
5. Do not encode target names, domains, package names, bundle ids, or app ids as platforms.

## Artifact kind versus category

`category` answers “what role does this artifact play?”

`kind` answers “what is the file/data shape?”

Examples:

| Path | Category | Kind |
| --- | --- | --- |
| `workspace/rebuild-plan.json` | `workspace` | `json` |
| `rebuild/sign_rebuild.py` | `rebuild` | `rebuild` |
| `reports/demo-final-report.md` | `report` | `markdown` |
| `workspace/android-hook-timeline.json` | `hook-timeline` | `json` |
| `workspace/ios-static-summary.json` | `static-analysis` | `json` |
| `workspace/mini-program-request-bridge.json` | `network` | `json` |

Do not use `kind` to smuggle platform or transport information. That belongs in `target_platforms` and `producer_transport`.

## Redaction expectations

Platform-neutral categories do not weaken redaction requirements.

- `runtime-context`, `hook-timeline`, `network`, and `session` can be sensitive.
- Public artifacts should prefer shape summaries, hashes, redacted values, and local-only paths.
- Secrets, cookies, tokens, account sessions, device identifiers, keychain values, proprietary source, APK/IPA/package dumps, and private bridge payloads must not be committed to public fixtures.

## Implementation guidance

When adding a backend:

1. Pick the closest category from `PLATFORM_NEUTRAL_ARTIFACT_CATEGORIES`.
2. Keep Web-compatible categories unchanged for existing outputs.
3. Add category-specific docs if a new category is genuinely needed.
4. Add tests for exported category constants or manifest examples.
5. Keep `workspace/backend-artifact-manifest.json` backward compatible.

If a future adapter needs more precision, put the detail in `metadata`, for example:

```json
{
  "category": "hook-timeline",
  "kind": "json",
  "target_platforms": ["android"],
  "metadata": {
    "hook_runtime": "frida",
    "language_surface": "java+jni",
    "redaction": "argument-shapes-only"
  }
}
```
