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

`legacy-mcp` is the explicit backend id; `mcp` and `jsreverser-mcp` remain deprecated runnable compatibility aliases for the transition window.

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

Status: contract and provider skeleton implemented; real browser smoke verified locally via Playwright using the system Chrome executable path; Playwright-managed browser download remains environment-dependent.

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

- Keep the Playwright-managed browser binary installation path documented for environments that allow it.
- Re-run headed/headless smoke against a freshly installed Playwright Chromium binary when available to confirm the package-managed browser path as well.

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

Status: minimal runtime implemented and registered; `remote-cdp` smoke path, advanced BrowserProvider option forwarding, and runtime-eval candidate validation baseline are implemented. Playwright and CloakBrowser real browser smoke have been verified locally.

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
- `remote-cdp` is implemented as a BrowserProvider smoke path for existing Chrome DevTools endpoints.
- CLI now accepts `--browser`, `--browser-profile-dir`, `--browser-headless`, `--browser-executable-path`, `--browser-args`, `--browser-humanize`, `--browser-proxy`, `--browser-locale`, and `--browser-timezone`.
- Unit tests: `tests.test_native_web_runtime`, `tests.test_remote_cdp_provider`.

Remaining validation:

- Re-run `reverse-agent-demo --runtime native-web --browser playwright-chromium` against a freshly installed Playwright browser binary when available, to confirm the package-managed browser path in addition to the system Chrome smoke.
- Keep `--browser-humanize`, `--browser-locale`, and `--browser-timezone` covered by real CloakBrowser smoke; validate `--browser-proxy` / `--browser-geoip` only in a controlled proxy environment.
- Ensure backend manifest continues to carry provider metadata in downstream artifact entries.

### Phase 5: CloakBrowser provider

Status: provider skeleton, optional dependency, browser-provider doctor metadata checks, real launch smoke, persistent-context smoke, connect-mode baseline, and native-web fixture smoke are verified locally.

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
- Real `reverse-agent-doctor --browser cloakbrowser --launch-browser-smoke` passes locally.
- Real persistent-context smoke with `--browser-profile-dir` passes locally.
- Real `reverse-agent-demo --runtime native-web --browser cloakbrowser` fixture smoke passes locally and emits native collector artifacts.

Remaining validation:

- Keep the real browser smoke path documented for environments that can also run CloakBrowser manually.
- Maintain the provider / doctor / collector capability gates as the browser wrapper evolves.
- Keep `docs/runtime/cloakbrowser-provider.md` updated after future binary or wrapper changes.

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
- BrowserProvider-backed runtime eval can emit `function-candidates.json`, `function-validations.json`, and `function-validation-summary.json` without going through MCP.

### Phase 7: Native artifact parity

Status: native DOM, console, script inventory, navigation evidence, and candidate validation evidence are mapped to workspace artifacts; related tests pass locally.

Deliverables:

- `workspace/dom-snapshot.json`
- `workspace/console-messages.json`
- `workspace/script-inventory.json`
- `workspace/navigation-events.json`
- `workspace/function-candidates.json`
- `workspace/function-validations.json`
- `workspace/function-validation-summary.json`
- backend manifest metadata containing `browser_provider` and `browser_provider_transport` when available

Acceptance:

- Native Web fake-provider pipeline writes the new workspace artifacts.
- Existing legacy MCP artifact mappings remain unchanged.
- Manifest entries expose provider metadata without secrets.

### Phase 8: CDP-enhanced collectors

Status: CDP event cache and metadata collector implemented and tested locally; script source fallback now uses the provider-neutral script inventory, WebSocket frame fallback can consume runtime hook timeline events when CDP frame events are unavailable, and `remote-cdp` provides a real smoke path against an existing Chrome DevTools endpoint. Playwright and CloakBrowser real browser smoke are both verified locally.

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

Status: hook baseline, WebSocket send/message capture, target-function wrapper baseline, webpack-like module export hook baseline, module discovery baseline with script inventory, read-only `require.c` / `require.m` runtime cache introspection, and explicit custom object runtime / module federation exposed-module function-path candidates, source-level logpoint baseline with bundle offset, Source Map exact, GLB bias, sourceRoot, and indexed section remap support, provider-neutral BreakpointManager baseline, in-process paused-session registry baseline, paused-session continuation preflight, durable paused-session snapshot inspect-only baseline, native-web runtime-eval candidate validation, basic paused/callframe breakpoint smoke, explicit evaluateOnCallFrame baseline, callframe evaluation policy baseline, callframe mutation audit baseline, closure-scope function discovery baseline, page-level coarse mutation audit baseline, MutationObserver timeline baseline around an explicit trigger, debugger step-control baseline, single-run debugger timeline baseline, native-web recon flow timeline baseline, explicit flow timeline continuation baseline, conservative flow timeline correlation hints, conservative flow timeline correlation groups, group verification readiness, manual stitch candidates, review-gated stitch proposals, evidence-promotion review requirement extraction, review gate blocking for pending stitch proposals, reviewer-approved stitched-flow materialization baseline, and auto-stitch dry-run scoring records, conservative policy decision gates, plan-only materialization plans, explicit-review-only auto-stitch materialization results, and materialization audit / rollback-plan baselines, review-only auto-stitch conflict resolution records, and transaction-log-only materialization transaction records for manual stitch candidates are implemented and tested locally. Cross-process live CDP paused execution continuation, arbitrary custom loader traversal / async chunk graph / execution-style module federation analysis, automatic wrapper hooks for arbitrary closure-internal functions beyond the paused-callframe evidence baseline, source-map name resolution / complex URL semantics / complex indexed section semantics, JS heap fine-grained mutation auditing, object graph diff, and automatic full cross-request timeline materialization without explicit review approval, full conflict resolver state-machine integration, true automatic rollback execution, and rollback review gate recompute remain future debugger-scope work; native-web recon writes `flow-timeline.json` from baseline collector fragments, annotates entries with request / URL / method / initiator / hook / candidate correlation hints, derives `correlation_groups` for shared hints, and marks each group with `verification.status`, evidence booleans, and `missing_for_ready`, promotes reviewable groups into manual-only `stitch_candidates`, scores those candidates through dry-run-only `auto_stitch_dry_runs` with `confidence_score`, `score_reasons`, `conflict_reasons`, `review_required=true`, `would_materialize=false`, and `automatic_stitching=false`, evaluates `auto_stitch_policy_decisions` / `auto_stitch_policy_summary` as a conservative review-gate decision layer, produces plan-only `auto_stitch_materialization_plans` / `auto_stitch_materialization_summary` for policy-eligible decisions without writing artifacts, materializes only explicitly approved `auto_stitch_materialization_review_decisions` into `auto_stitch_materialization_results` and reviewer-approved `stitched-flow.json` baselines with `automatic_stitching=false`, emits `auto_stitch_materialization_audit_entries` and `auto_stitch_materialization_rollback_plans` with `automatic_rollback=false`, promotes only `ready_for_manual_stitch_review` candidates into pending-review `stitch_proposals`, surfaces those pending proposals as evidence-level review requirements, blocks delivery through `review-gate.json` with `review_stitch_proposals_before_delivery`, materializes explicitly approved proposals as `stitched-flow.json` with `automatic_stitching=false`, and keeps explicit `flow-timeline` continuation as a source-fragment normalization baseline rather than automatic stitching.

Deliverables:

- `hooks/fetch_xhr.py`
- `hooks/cookie.py`
- `hooks/anti_debug.py`
- `hooks/breakpoints.py`
- `hooks/function_hooks.py`
- `hooks/module_hooks.py`
- `hooks/source_logpoints.py`
- WebSocket send/message hook capture through the shared hook timeline.
- `virtual://workspace/function-hooks.json` and `virtual://workspace/function-hook-timeline.json` target-function hook artifact refs / evidence mapping
- `virtual://workspace/module-hooks.json` and `virtual://workspace/module-hook-timeline.json` explicit webpack-like module export hook artifact refs / evidence mapping
- `virtual://workspace/module-registry.json` and `virtual://workspace/module-candidates.json` module discovery artifact refs / evidence mapping, including runtime kinds, runtime paths, and module counts for webpack-like `require.c` / `require.m`, custom object runtime, and module federation exposed-module baselines
- `virtual://workspace/source-logpoints.json` and `virtual://workspace/source-logpoint-timeline.json` source logpoint artifact refs / evidence mapping
- retained paused-session registry baseline via `pause_session_id` and `paused-session` follow-up actions, with `continuation_preflight` reporting same-process live availability before and after requested actions
- durable paused-session snapshot inspect-only baseline via `persist_paused_session` / `paused_session_store_dir`, with inspect-only `continuation_preflight` and structured `live_paused_session_required` / `status=action_blocked` rejection for cross-process resume / step / evaluate attempts
- `virtual://workspace/breakpoints.json` protection artifact ref / evidence mapping
- `virtual://workspace/debugger-paused.json` and `virtual://workspace/callframes.json` breakpoint smoke artifact refs
- `virtual://workspace/callframe-evaluations.json` artifact ref when explicit callframe evaluations are requested
- `virtual://workspace/closure-functions.json` and `virtual://workspace/closure-function-candidates.json` artifact refs when explicit closure-scope function discovery is requested
- `virtual://workspace/mutation-audit.json` artifact ref with callframe evaluation side-effect risk summaries
- `virtual://workspace/page-mutation-audit.json` artifact ref with explicit page before/after mutation summary diffs
- `virtual://workspace/mutation-observer-timeline.json` artifact ref with explicit-trigger MutationObserver DOM mutation records
- `virtual://workspace/debugger-actions.json` artifact ref when explicit debugger step-control actions are requested
- `virtual://workspace/debugger-session.json` artifact ref with selected callFrame and pause lifecycle metadata
- `virtual://workspace/debugger-timeline.json` artifact ref with ordered single-run debugger timeline entries
- `virtual://workspace/flow-timeline.json` artifact ref with native-web recon flow entries, conservative per-entry `correlation` hints, non-authoritative `correlation_groups`, per-group verification readiness, manual-only `stitch_candidates`, dry-run-only `auto_stitch_dry_runs`, conservative `auto_stitch_policy_decisions`, plan-only `auto_stitch_materialization_plans`, explicit-review-only `auto_stitch_materialization_results`, materialization audit / rollback-plan entries, review-gated `stitch_proposals`, and explicit cross-request flow continuation entries
- `workspace/evidence-promotion.json` / `workspace/review-gate.json` handling for pending `stitch_proposals`, including `flow_timeline_stitch_proposal_pending_review` and `next_action=review_stitch_proposals_before_delivery`
- `auto_stitch_dry_runs` dry-run scoring / `auto_stitch_policy_decisions` policy gate records with conflict summaries and fixed `would_materialize=false` / `automatic_stitching=false` safeguards
- `virtual://workspace/auto-stitch-materialization-results.json` / `workspace/auto-stitch-materialization-results.json` baseline for explicitly approved auto-stitch materialization plans, with `writes_artifact=true` and `automatic_stitching=false`
- `virtual://workspace/stitched-flow-materialization-audit.json` / `workspace/stitched-flow-materialization-audit.json` baseline for materialization audit entries
- `virtual://workspace/stitched-flow-rollback-plan.json` / `workspace/stitched-flow-rollback-plan.json` baseline for manual rollback planning, with `automatic_rollback=false`
- `virtual://workspace/stitched-flow.json` / `workspace/stitched-flow.json` baseline for explicitly approved `stitch_review_decisions` or `auto_stitch_materialization_review_decisions`, with `stitching=true` and `automatic_stitching=false`
- runtime-observe playbook integration.

Acceptance:

- Fetch/XHR hook can capture request parameters before app encryption/signing wrappers send them.
- Anti-debug patches are minimal and auditable.
- Breakpoint features are behind provider capability checks and only run for explicit protection/debug requests.
- Hook output is emitted as normalized evidence and artifact files.
- Target-function hook baseline is limited to globally reachable paths such as `window.buildSign`; module discovery baseline is limited to best-effort source inventory extraction, read-only webpack-like `require.c` / `require.m` runtime cache and registry introspection, and explicit custom object runtime / module federation exposed-module snapshots that produce function-path candidates; it still does not traverse arbitrary custom loaders, async chunk graphs, or execute federation `get/init` flows; source-level logpoint baseline can remap generated offsets and Source Map v3 original locations with exact, GLB bias, sourceRoot, and indexed section support, but remains limited to script URL / line-number style breakpoints; retained paused-session live continuation is in-process only and is exposed through `continuation_preflight`, while durable paused-session snapshots are inspect-only and cannot resume / step / evaluate the original CDP paused execution; page-level mutation audit is a coarse before/after summary while MutationObserver timeline is an explicit-trigger finite DOM record baseline rather than JS heap timeline or object graph diff; source-map name resolution / complex URL semantics / complex indexed section semantics, JS heap fine-grained mutation audit, arbitrary runtime cache introspection, automatic wrapper hook support for arbitrary closure-internal functions, automatic full cross-request timeline materialization without explicit review approval, richer conflict resolver / true rollback executor, and cross-process live CDP paused execution continuation are intentionally separate follow-up capabilities; native-web recon flow timeline, per-entry correlation hints, conservative correlation groups, group verification readiness, manual stitch candidates, review-gated stitch proposals, reviewer-approved stitched-flow materialization, and explicit flow timeline continuation are available as baselines.

### Phase 10: MCP legacy downgrade

Status: implemented locally. `legacy-mcp` is the canonical backend id; `mcp` and `jsreverser-mcp` remain deprecated compatibility aliases and now emit CLI warnings when explicitly selected. Doctor supports `--legacy-mcp`; `--check-mcp` is kept only as a deprecated compatibility flag. `native-web` remains the README quickstart recommendation.

Deliverables:

- Rename docs wording from `mcp` preferred path to `legacy-mcp` compatibility path.
- Keep CLI alias `mcp` temporarily for backward compatibility, but warn users to migrate to `legacy-mcp`.
- Update doctor:
  - default checks native browser provider.
  - `--legacy-mcp` checks jsreverser-mcp.
- Move MCP smoke docs under legacy runtime section.

Acceptance:

- README quickstart uses `native-web`.
- MCP smoke remains runnable for users who still need it.
- Deprecated MCP aliases warn without breaking existing scripts.
- Public CI does not require MCP.
- Native Web runtime is the default recommendation.

### Phase 10.1: Runtime backend entry-point discovery

Status: implemented. `RuntimeBackendRegistry.load_entry_points()` loads backend registrations from the `reverse_deepagent.runtime_backends` Python entry-point group, validates registration / capability id consistency, and keeps backend factories uncalled during metadata listing. `packages/reverse-deepagent-legacy-mcp/` owns the optional legacy MCP registration / factory, config object, and stdio bridge implementation, while `reverse_deepagent.runtime.legacy_mcp` is a compatibility shim with alias warnings, doctor proxy, plugin delegation, and structured install guidance. Core no longer ships a built-in legacy MCP factory fallback or stdio MCP transport; if the optional package is missing, `legacy-mcp` / `mcp` runtime construction returns install guidance and does not start managed Chrome or MCP.

Deliverables:

- `RUNTIME_BACKEND_ENTRY_POINT_GROUP` exported from `reverse_deepagent.runtime`.
- `RuntimeBackendRegistry.load_entry_points()` supports a single `RuntimeBackendRegistration`, a callable returning registrations, or an iterable of registrations.
- `build_default_runtime_registry(include_entry_points=True, include_legacy_mcp=True)` loads external backend registrations by default, keeps a deterministic entry-point opt-out for tests, can explicitly exclude the built-in legacy MCP registration, and only falls back to the built-in legacy MCP registration when no external `legacy-mcp` entry point exists.
- Unit tests cover plugin registration, callable multi-registration, invalid payload errors, entry-point load errors, capability id mismatch rejection, external `legacy-mcp` entry-point loading, optional plugin package metadata, core shim install guidance / plugin delegation, missing-plugin CLI guidance, Chrome lifecycle ordering, and the invariant that backend factories are not invoked during metadata listing.

Acceptance:

- External runtime backend packages have a stable discovery seam.
- Metadata listing remains free of browser, MCP, device-tool, and network session side effects.
- Legacy MCP implementation is now optional-package owned; coordinator no longer owns MCP registration details inline, core no longer ships stdio MCP transport, and missing-plugin paths are guidance-only.

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
8. Optional runtime backends can be discovered through package entry points without making the coordinator depend on plugin internals.


## Current active execution snapshot

See `.codex/plans/browser-provider-mcp-deprecation-plan.md` for the detailed Step 18 execution record. Current status: auto-stitch conflict resolver baseline is implemented as review-only output with `auto_stitch_conflict_resolutions`, `auto_stitch_conflict_resolution_summary`, and `virtual://workspace/auto-stitch-conflict-resolutions.json`; it does not enable automatic stitching or materialization.


Step 19 execution record: materialization transaction log baseline is implemented as transaction-log-only output with `auto_stitch_materialization_transactions`, `auto_stitch_materialization_transaction_summary`, and `virtual://workspace/stitched-flow-materialization-transactions.json`; it aggregates result / audit / rollback-plan links but does not execute rollback or recompute review gates.
