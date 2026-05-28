# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses semantic-ish version tags while it is still in an early research/demo stage.

## [Unreleased]

### Added

- Local Web sign fixture profiles for `md5` and `sha1`, covering `md5_keyword_timestamp` and `sha1_keyword_timestamp` rebuild paths.
- More realistic Web sign fixture profiles for `webpack-minified`, `token-chain`, and `hybrid-context`, covering bundled source, bootstrap-token, and multi-context binding scenarios.
- Multi-sample `runtime-context-diff.json` generation with stable / volatile key classification and change summaries.
- Rebuild strategy registry abstraction with ordered metadata for deterministic fixture, template, crypto hash, and encoding detectors.
- Self-hosted MCP smoke workflow documentation, fixture profile options, and explicit `--jsreverser-mcp-command` wiring.
- Self-hosted MCP smoke continuous canary support with scheduled runs, profile sets, runner preflight, step summaries, and artifact upload.
- `RuntimeBackendCapabilities` schema and `describe_capabilities()` runtime metadata for mock and JSReverser MCP backends.
- `RuntimeBackendRegistry` factory with `mock` / `mcp` backend registrations and JSON-serializable metadata listing.
- `RuntimeArtifactManifest` / `RuntimeArtifactManifestEntry` schemas and generated `workspace/backend-artifact-manifest.json`.
- `JSReverserMcpConfig` for serialized MCP command, browser URL, timeout, backend metadata, and sampling configuration.
- Runtime adapter pluginization contract documentation for current Web backends and future Android / iOS / mini-program expansion.
- `reverse_deepagent.strategies` package with pluggable detector registry while keeping rebuild output compatible.
- Structured strategy `confidence_score` payload with numeric score, positive markers, and caveats while preserving the legacy `confidence` field.
- `STRATEGY_SAMPLE_CORPUS` covering fixture reducer, hash, HMAC, Base64, and URL encoding strategy samples with generated rebuild self-check coverage.
- Machine-readable rebuild `review_hints` for pure, context-aware, and manual-port / partial generated artifacts.
- WASM / VM / heavy obfuscation triage contract documenting when protected flows must remain partial or runtime-assisted instead of fake pure-Python rebuilds.
- Android runtime adapter interface draft for future ADB / Frida / static APK backends without Web-only browser session assumptions.
- iOS runtime adapter interface draft for future Frida / simulator / static IPA backends without Web-only browser session assumptions.
- Mini-program runtime adapter interface draft for future developer-tool / JSCore / request-bridge backends without normal-browser assumptions.
- Platform-neutral runtime artifact category vocabulary exported from `reverse_deepagent.runtime` and documented for Web / Android / iOS / mini-program manifests.
- Web-specific runtime assumptions documented and isolated so future platform adapters do not inherit browser session, Chrome debug, storage, or URL replay semantics by accident.

## [0.1.0] - 2026-05-27

### Added

- Initial public release of `reverse-deepagent`.
- DeepAgents-based reverse-engineering coordinator scaffold.
- Router, Web recon, protector, and rebuild delivery subagent wiring.
- Runtime adapter boundary for JSReverser / MCP-backed browser observation.
- Managed Chrome debug lifecycle scripts with configurable port, profile, state dir, and extra args.
- Local deterministic Web sign fixture with profiles:
  - `default`
  - `sha256`
  - `base64`
  - `context-localstorage`
  - `context-cookie`
  - `context-navigator`
- Function candidate generation from source / request / initiator evidence.
- Runtime validation and replay readiness summary artifacts.
- Pure-Python rebuild bundle generation:
  - `rebuild/sign_rebuild.py`
  - `rebuild/replay_demo.py`
  - `rebuild/scrapy_middleware.py`
- Strategy detection for deterministic fixture, hash, HMAC, base64, and URL encoding flows.
- Runtime context capture for localStorage, sessionStorage, cookie, navigator, timezone, and related browser environment fields.
- Context-aware rebuild rendering for:
  - `localStorage.device_id`
  - `cookie.device_id`
  - `navigator.userAgent`
- `runtime-context-diff.json` single-sample stability artifact.
- Public CI for mock / pure-Python unit and smoke coverage.
- Public repository maintenance files: license, contributing guide, security policy, issue templates, and CI workflow.

### Changed

- Replaced local absolute defaults with repo-relative, home-relative, or environment-variable-backed paths.
- Added fallback route manifests so the public package does not require a local `~/.codex/skills/js-reverse` checkout for basic tests.
- Made MCP lifecycle tests conditional on local JSReverser MCP availability.

### Verified

- Local full test suite: `python -m unittest discover -s tests -v`.
- GitHub Actions CI on `main`.
- Real local MCP fixture smoke for context-aware cookie and navigator profiles before public release.

### Known limitations

- MCP-backed integration tests require a local JSReverser MCP binary and a Chrome-compatible desktop environment.
- MCP-backed runtime context sampling depends on the target page being stable enough for repeated storage/environment probes.
- Android / iOS / mini-program adapters are design targets but not implemented in v0.1.0.
- Generated rebuild scripts intentionally cover recognized strategies only; unknown or heavily obfuscated algorithms still require manual porting or runtime-backed execution.
