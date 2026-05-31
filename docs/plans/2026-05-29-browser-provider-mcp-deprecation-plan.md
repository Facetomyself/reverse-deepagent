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

Status: hook baseline, WebSocket send/message capture, target-function wrapper baseline, webpack-like module export hook baseline, module discovery baseline with script inventory, read-only `require.c` / `require.m` runtime cache introspection, and explicit custom object runtime / module federation exposed-module function-path candidates, source-level logpoint baseline with bundle offset, Source Map exact, GLB bias, sourceRoot, and indexed section remap support, provider-neutral BreakpointManager baseline, in-process paused-session registry baseline, paused-session continuation preflight, durable paused-session snapshot inspect-only baseline, native-web runtime-eval candidate validation, basic paused/callframe breakpoint smoke, explicit evaluateOnCallFrame baseline, callframe evaluation policy baseline, callframe mutation audit baseline, closure-scope function discovery baseline, page-level coarse mutation audit baseline, MutationObserver timeline baseline around an explicit trigger, debugger step-control baseline, single-run debugger timeline baseline, native-web recon flow timeline baseline, explicit flow timeline continuation baseline, conservative flow timeline correlation hints, conservative flow timeline correlation groups, group verification readiness, manual stitch candidates, review-gated stitch proposals, evidence-promotion review requirement extraction, review gate blocking for pending stitch proposals, reviewer-approved stitched-flow materialization baseline, and auto-stitch dry-run scoring records, conservative policy decision gates, plan-only materialization plans, explicit-review-only auto-stitch materialization results, and materialization audit / rollback-plan baselines, review-only auto-stitch conflict resolution records, transaction-log-only materialization transaction records, dry-run / explicit-review-only rollback execution records, post-rollback review gate recompute baseline records, physical rollback dry-run diff records, explicit-review-only physical rollback mutation records, and post-physical-rollback review gate rerun records, standard review gate replacement records, post-replacement delivery guard rerun records, and artifact-model final delivery package records, explicit-review-only transaction commit record baselines, and local delivery executor contract baseline and backend artifact manifest mutation policy baseline plus backend manifest in-place mutation preflight baseline plus explicit-review-only backend manifest in-place mutation executor baseline and cross-run recovery preflight baseline for manual stitch candidates are implemented and tested locally. Cross-process live CDP paused execution continuation, arbitrary custom loader traversal / async chunk graph / execution-style module federation analysis, automatic wrapper hooks for arbitrary closure-internal functions beyond the paused-callframe evidence baseline, source-map name resolution / complex URL semantics / complex indexed section semantics, JS heap fine-grained mutation auditing, object graph diff, and automatic full cross-request timeline materialization without explicit review approval, full conflict resolver state-machine integration, write-capable cross-run rollback executor / physical state machine beyond the read-only rollback state baseline, stronger distributed transaction locking beyond the local transaction lock baseline, advanced adaptive retry / secondary rate-limit policies and third-party external delivery providers remain future debugger-scope work; GitHub Release explicit asset delete + replacement upload is implemented behind approval flags; native-web recon writes `flow-timeline.json` from baseline collector fragments, annotates entries with request / URL / method / initiator / hook / candidate correlation hints, derives `correlation_groups` for shared hints, and marks each group with `verification.status`, evidence booleans, and `missing_for_ready`, promotes reviewable groups into manual-only `stitch_candidates`, scores those candidates through dry-run-only `auto_stitch_dry_runs` with `confidence_score`, `score_reasons`, `conflict_reasons`, `review_required=true`, `would_materialize=false`, and `automatic_stitching=false`, evaluates `auto_stitch_policy_decisions` / `auto_stitch_policy_summary` as a conservative review-gate decision layer, produces plan-only `auto_stitch_materialization_plans` / `auto_stitch_materialization_summary` for policy-eligible decisions without writing artifacts, materializes only explicitly approved `auto_stitch_materialization_review_decisions` into `auto_stitch_materialization_results` and reviewer-approved `stitched-flow.json` baselines with `automatic_stitching=false`, emits `auto_stitch_materialization_audit_entries` and `auto_stitch_materialization_rollback_plans` with `automatic_rollback=false`, produces dry-run `auto_stitch_rollback_execution_plans`, records only explicitly approved logical rollback results without mutating `stitched-flow.json`, emits blocking `auto_stitch_rollback_review_gate_recomputations` that do not replace the standard review gate, emits dry-run `auto_stitch_physical_rollback_dry_run_diffs` that describe would-remove / manifest impact, applies explicitly approved `auto_stitch_physical_rollback_review_decisions` into `auto_stitch_physical_rollback_results` by removing matching entries from the current `stitched_flows` artifact model, emits blocking `auto_stitch_post_physical_rollback_review_gate_reruns` without replacing the standard review gate, records explicitly approved `auto_stitch_standard_review_gate_replacement_results`, emits `auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns`, emits artifact-model `auto_stitch_post_standard_review_gate_replacement_final_delivery_packages`, records explicit-review-only `auto_stitch_transaction_commit_results`, promotes only `ready_for_manual_stitch_review` candidates into pending-review `stitch_proposals`, surfaces those pending proposals as evidence-level review requirements, blocks delivery through `review-gate.json` with `review_stitch_proposals_before_delivery`, materializes explicitly approved proposals as `stitched-flow.json` with `automatic_stitching=false`, and keeps explicit `flow-timeline` continuation as a source-fragment normalization baseline rather than automatic stitching.

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
- `virtual://workspace/stitched-flow-rollback-executions.json` / `workspace/stitched-flow-rollback-executions.json` baseline for rollback execution dry-run plans and explicitly approved logical rollback results, with `physical_artifact_mutated=false` and `automatic_rollback=false`
- `virtual://workspace/review-gate-after-rollback.json` / `workspace/review-gate-after-rollback.json` baseline for post-rollback review gate recomputation records, with `blocked=true`, `delivery_allowed=false`, and `does_not_replace_review_gate=true`
- `virtual://workspace/stitched-flow-physical-rollback-diff.json` / `workspace/stitched-flow-physical-rollback-diff.json` baseline for physical rollback dry-run diffs, with `dry_run_only=true`, `would_mutate_if_approved=true`, and `target_artifact_mutated=false`
- `virtual://workspace/stitched-flow.json` / `workspace/stitched-flow.json` baseline for explicitly approved `stitch_review_decisions` or `auto_stitch_materialization_review_decisions`, with `stitching=true` and `automatic_stitching=false`
- `virtual://workspace/review-gate-replacement-results.json` / `workspace/review-gate-replacement-results.json`, `virtual://workspace/delivery-guard-after-review-gate-replacement.json` / `workspace/delivery-guard-after-review-gate-replacement.json`, and `virtual://workspace/final-delivery-package-after-review-gate-replacement.json` / `workspace/final-delivery-package-after-review-gate-replacement.json` and `virtual://workspace/final-delivery-transaction-commit.json` / `workspace/final-delivery-transaction-commit.json` baselines for explicit review gate replacement, delivery guard rerun, artifact-model final delivery packaging, and explicit-review-only transaction commit record after physical rollback, with `automatic_delivery=false`, `external_delivery_performed=false`, `filesystem_artifact_mutated=false`, and `cross_run_transaction_committed=false`
- runtime-observe playbook integration.

Acceptance:

- Fetch/XHR hook can capture request parameters before app encryption/signing wrappers send them.
- Anti-debug patches are minimal and auditable.
- Breakpoint features are behind provider capability checks and only run for explicit protection/debug requests.
- Hook output is emitted as normalized evidence and artifact files.
- Target-function hook baseline is limited to globally reachable paths such as `window.buildSign`; module discovery baseline is limited to best-effort source inventory extraction, read-only webpack-like `require.c` / `require.m` runtime cache and registry introspection, and explicit custom object runtime / module federation exposed-module snapshots that produce function-path candidates; it still does not traverse arbitrary custom loaders, async chunk graphs, or execute federation `get/init` flows; source-level logpoint baseline can remap generated offsets and Source Map v3 original locations with exact, GLB bias, sourceRoot, and indexed section support, but remains limited to script URL / line-number style breakpoints; retained paused-session live continuation is in-process only and is exposed through `continuation_preflight`, while durable paused-session snapshots are inspect-only and cannot resume / step / evaluate the original CDP paused execution; page-level mutation audit is a coarse before/after summary while MutationObserver timeline is an explicit-trigger finite DOM record baseline rather than JS heap timeline or object graph diff; source-map name resolution / complex URL semantics / complex indexed section semantics, JS heap fine-grained mutation audit, arbitrary runtime cache introspection, automatic wrapper hook support for arbitrary closure-internal functions, automatic full cross-request timeline materialization without explicit review approval, richer conflict resolver / cross-run physical rollback transaction state machine / stronger distributed transaction locking beyond local idempotency guard baseline / external delivery executor, and cross-process live CDP paused execution continuation are intentionally separate follow-up capabilities; native-web recon flow timeline, per-entry correlation hints, conservative correlation groups, group verification readiness, manual stitch candidates, review-gated stitch proposals, reviewer-approved stitched-flow materialization, and explicit flow timeline continuation are available as baselines.

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

Step 20 execution record: rollback execution baseline is implemented as dry-run / explicit-review-only output with `auto_stitch_rollback_execution_plans`, `auto_stitch_rollback_execution_results`, and `virtual://workspace/stitched-flow-rollback-executions.json`; default plans do not revert anything and explicit approvals only record logical rollback results without physical artifact mutation.

Step 21 execution record: post-rollback review gate recompute baseline is implemented as blocking output with `auto_stitch_rollback_review_gate_recomputations`, `auto_stitch_rollback_review_gate_recomputation_summary`, and `virtual://workspace/review-gate-after-rollback.json`; it does not replace `workspace/review-gate.json`, does not allow delivery, and still requires standard review gate rerun before delivery.

Step 22 execution record: physical rollback dry-run diff baseline is implemented with `auto_stitch_physical_rollback_dry_run_diffs`, `auto_stitch_physical_rollback_dry_run_diff_summary`, and `virtual://workspace/stitched-flow-physical-rollback-diff.json`; it describes would-remove entries, manifest impact, and review requirements but does not mutate `stitched-flow.json` or replace `review-gate.json`.

Step 23 execution record: explicit-review-only physical rollback mutation baseline is implemented with `auto_stitch_physical_rollback_review_decisions`, `auto_stitch_physical_rollback_results`, `auto_stitch_physical_rollback_result_summary`, and `virtual://workspace/stitched-flow-physical-rollback-results.json`; approved physical rollback decisions remove matching entries from the current `stitched_flows` artifact model while keeping `automatic_rollback=false` and without replacing `workspace/review-gate.json`.

Step 24 execution record: post-physical-rollback review gate rerun baseline is implemented with `auto_stitch_post_physical_rollback_review_gate_reruns`, `auto_stitch_post_physical_rollback_review_gate_rerun_summary`, and `virtual://workspace/review-gate-after-physical-rollback.json`; it blocks delivery after approved physical rollback, records that the standard review gate must be rerun, and still does not replace `workspace/review-gate.json`.

Step 25 execution record: standard review gate replacement baseline is implemented with `auto_stitch_standard_review_gate_replacement_review_decisions`, `auto_stitch_standard_review_gate_replacement_results`, `auto_stitch_standard_review_gate_replacement_summary`, and `virtual://workspace/review-gate-replacement-results.json`; explicit approval records that the standard `workspace/review-gate.json` artifact model has been replaced after physical rollback; Step 26 now adds a delivery guard rerun baseline, while automatic delivery, rollback, and cross-run transaction commit remain disabled.


Step 26 execution record: delivery guard rerun after standard review gate replacement baseline is implemented with `auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns`, `auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary`, and `virtual://workspace/delivery-guard-after-review-gate-replacement.json`; replacement results now produce a guard-rerun record with `delivery_guard_passed=true` and `delivery_allowed=true` while keeping `automatic_delivery=false`. Step 27 now packages that passed guard into an artifact-model final delivery package, while manual external delivery and cross-run transaction commit remain future work.

Step 27 execution record: final delivery package after delivery guard rerun baseline is implemented with `auto_stitch_post_standard_review_gate_replacement_final_delivery_packages`, `auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary`, and `virtual://workspace/final-delivery-package-after-review-gate-replacement.json`; delivery guard passed records now produce a package artifact with `package_ready=true`, `final_delivery_packaged=true`, and `delivery_allowed=true`, while keeping `automatic_delivery=false`, `external_delivery_performed=false`, `cross_run_transaction_committed=false`, and `manifest_revision_committed=false`.

Step 28 execution record: final delivery transaction commit record baseline is implemented with `auto_stitch_transaction_commit_review_decisions`, `auto_stitch_transaction_commit_results`, `auto_stitch_transaction_commit_summary`, and `virtual://workspace/final-delivery-transaction-commit.json`; explicit transaction commit approval records `artifact_model_transaction_commit_recorded=true`, while keeping `cross_run_transaction_committed=false`, `manifest_revision_committed=false`, `filesystem_artifact_mutated=false`, `external_delivery_performed=false`, and `automatic_delivery=false`.

Step 29 execution record: local delivery executor contract baseline is implemented with `LocalDeliveryExecutor`, `DeliveryExecutorConfig`, `DeliveryReceipt`, `DeliveryTransactionJournal`, `execute_local_delivery`, and indexed-only `/workspace/delivery/` routes for `workspace/delivery-receipt.json` plus `workspace/delivery-transaction-journal.json`. The delivery subagent now exposes `execute_local_delivery`; dry-run remains the default and produces no filesystem mutation, while explicit `mode=apply` only copies reviewed local files and writes receipt / journal. This is not an external delivery executor, does not upload or push artifacts, and keeps `manifest_revision_committed=false`.

Step 30 execution record: local delivery manifest revision baseline is implemented behind explicit `commit_manifest_revision=true`. In dry-run it only returns a planned `DeliveryManifestRevision`; in apply mode it writes `delivery-manifest-revision.json`, marks `manifest_revision_committed=true` in the local result and transaction journal, and keeps `backend_manifest_mutated=false` plus `external_delivery_performed=false`. This is a local delivery revision record, not a cross-run backend manifest mutation or recovery state machine.

Step 31 execution record: backend artifact manifest mutation policy baseline is implemented behind explicit `commit_backend_manifest_mutation=true`. In dry-run it only returns a planned `BackendManifestMutation`; in apply mode it writes `backend-artifact-manifest-mutation.json` plus `backend-artifact-manifest.patched.json`, records `backend_manifest_patch_written=true`, and keeps the source `workspace/backend-artifact-manifest.json` unchanged with `backend_manifest_mutated=false`, `external_delivery_performed=false`, and no cross-run transaction commit.

Step 32 execution record: backend manifest in-place mutation preflight baseline is implemented behind explicit `preflight_backend_manifest_in_place_mutation=true`. In dry-run it only returns a planned `BackendManifestInPlacePreflight`; in apply mode it writes `backend-artifact-manifest-preflight.json`, checks source manifest existence, optional expected source digest, local patched manifest availability, and duplicate artifact keys, while keeping `backend_manifest_mutated=false`, `external_delivery_performed=false`, and no cross-run transaction commit.

Step 33 execution record: backend manifest in-place mutation executor baseline is implemented behind explicit `approve_backend_manifest_in_place_mutation=true`. It requires apply mode, local patch written, preflight passed, and expected source digest matching the current source manifest; when approved it writes `backend-artifact-manifest.rollback.json`, writes `backend-artifact-manifest-in-place-mutation.json`, and mutates the standard backend artifact manifest in place while still keeping `external_delivery_performed=false` and `cross_run_transaction_committed=false`.

Step 34 execution record: backend manifest cross-run recovery preflight baseline is implemented behind explicit `preflight_backend_manifest_recovery=true`. It reads the previous local `delivery-transaction-journal.json`, in-place mutation record, patched manifest, rollback checkpoint, and current source manifest digest, writes `backend-artifact-manifest-recovery-preflight.json`, and reports `ready_for_review`, `blocked`, or `no_recovery_required` without restoring files, publishing external delivery, or committing a cross-run transaction.

Step 35 execution record: backend manifest cross-run transaction commit baseline is implemented behind explicit `commit_cross_run_transaction=true`. It requires apply mode, a previous local `delivery-transaction-journal.json`, a passing `backend-artifact-manifest-recovery-preflight.json`, matching source manifest digest, no previous external delivery, no duplicate cross-run commit, and an optional expected transaction id match; when approved it writes `backend-artifact-manifest-transaction-commit.json` and marks the previous journal with `cross_run_transaction_committed=true` plus `backend_manifest_transaction_commit_path`. It still does not publish external delivery, restore manifests by itself, or implement the full cross-run recovery / rollback transaction state machine.

Step 36 execution record: backend manifest recovery apply baseline is implemented behind explicit `apply_backend_manifest_recovery=true`. It requires apply mode, a previous local `delivery-transaction-journal.json`, a `ready_for_review` `backend-artifact-manifest-recovery-preflight.json`, matching expected transaction id when provided, no previous external delivery, no previous cross-run commit, no previous recovery, rollback checkpoint availability, and source / rollback digest consistency. When approved it writes `backend-artifact-manifest-recovery.json`, restores standard `backend-artifact-manifest.json` from `backend-artifact-manifest.rollback.json`, and marks the previous journal with `backend_manifest_recovered=true` plus `backend_manifest_recovery_path`. It still does not publish external delivery, does not perform automatic recovery, and is not the full cross-run recovery / rollback transaction state machine.

Step 37 execution record: ExternalDeliveryProvider contract baseline is implemented behind explicit `request_external_delivery=true`. It adds provider-neutral `ExternalDeliveryPackage` / `ExternalDeliveryResult` records, exports the pluggable `ExternalDeliveryProvider` protocol plus the built-in `ReviewOnlyExternalDeliveryProvider`, writes `external-delivery-result.json`, records `external_delivery_result_path` and `external_delivery_performed` in the delivery transaction journal, and exposes `request_external_delivery` / `external_delivery_provider_id` through `execute_local_delivery`. The default review-only provider always blocks with `external_delivery_provider_configured` and never uploads, pushes, publishes, or calls third-party systems; tests use a fake provider to prove a configured provider can mark `external_delivery_performed=true` without adding a real external integration.

Step 38 execution record: ExternalDeliveryProvider registry / entry-point discovery baseline is implemented. It adds `ExternalDeliveryProviderRegistry`, `ExternalDeliveryProviderRegistration`, `ExternalDeliveryProviderCapabilities`, `ExternalDeliveryProviderFactory`, the `reverse_deepagent.external_delivery_providers` entry-point group, and `build_default_external_delivery_provider_registry()`. The default registry registers `review-only` plus `noop` / `manual-handoff` aliases, loads provider registrations from entry points without invoking provider factories, rejects duplicate keys and capability id mismatches, and lets `LocalDeliveryExecutor` resolve `external_delivery_provider_id` through the registry when a provider object is not injected. It now ships built-in webhook, presigned object-storage, and GitHub Release JSON asset upload / explicit existing-release reuse / asset duplicate preflight baselines; asset overwrite / advanced adaptive provider retry policy and third-party release providers remain plugin follow-ups behind the registry contract.

Step 39 execution record: ExternalDeliveryProvider doctor / metadata CLI baseline is implemented with `reverse-agent-doctor --external-delivery-providers`, `ExternalDeliveryProviderRegistry.list_registration_metadata()`, and `external_delivery_provider_matrix`. The doctor output lists provider ids, aliases, the `reverse_deepagent.external_delivery_providers` entry-point group, transport, `review_only`, `supports_external_delivery`, summary counts, and a side-effect policy while skipping CDP port probes, not requiring MCP / Chrome, and not invoking provider factories. It now lists built-in webhook, presigned object-storage, and GitHub Release JSON asset upload / explicit existing-release reuse / asset duplicate preflight baselines without invoking provider factories; asset overwrite / advanced adaptive provider retry policy and third-party release providers remain plugin follow-ups behind the registry contract.

Step 40 execution record: external delivery idempotency / duplicate guard baseline is implemented. `DeliveryExecutorConfig` now accepts `external_delivery_idempotency_key` plus `allow_duplicate_external_delivery`; the idempotency key defaults to the transaction id and is written into package / journal metadata. When a previous `delivery-transaction-journal.json` or `external-delivery-result.json` in the same delivery root reports `external_delivery_performed=true`, a later external delivery request is blocked before invoking the provider factory / provider and writes `external-delivery-duplicate-guard.json`, while preserving the previous journal performed state and original external result path. An explicit `allow_duplicate_external_delivery=true` is required for a reviewed retry. This is a duplicate-call guard, not a full cross-run transaction state machine; webhook, presigned object-storage, and GitHub Release now exist as explicit provider baselines, while advanced adaptive provider retry policy / overwrite policies remain follow-ups.

Step 41 execution record: LocalArchiveExternalDeliveryProvider / filesystem-release baseline is implemented. The default external delivery registry now includes `local-archive` plus `filesystem-release` / `archive` aliases, and `reverse-agent-doctor --external-delivery-providers` reports it as `transport=filesystem`, `supports_external_delivery=true`, and `review_only=false` without invoking provider factories. `DeliveryExecutorConfig` now accepts `external_delivery_provider_config`, and `execute_local_delivery` exposes `external_delivery_provider_config_json` so provider-specific options such as `archive_root` can be passed through. In dry-run, local-archive is side-effect-free and returns a planned result; in apply mode it copies already delivered artifacts into a deterministic local archive release directory and writes `local-archive-manifest.json` plus `local-archive-checksums.json`, with paths recorded in `external-delivery-result.json` metadata. This is the first real external delivery provider boundary, but it is intentionally filesystem-only: it does not upload to network services, create GitHub Releases, bypass review, or bypass the duplicate guard / transaction limitations.

Step 42 execution record: ExternalDeliveryProvider config redaction / capability metadata guard baseline is implemented. Delivery now exports `external_delivery_metadata_has_secret_like_keys`, rejects secret-like keys in `ExternalDeliveryProviderRegistration` capability metadata before those rows can appear in doctor / registry metadata, and keeps runtime `external_delivery_provider_config` available only for provider construction. `ExternalDeliveryPackage.metadata` now contains `external_delivery_provider_config_summary` with configured state, total key count, non-secret key names, secret-like key count, and `raw_values_exported=false`, rather than raw provider config values. Tests prove capability metadata containing token / authorization-style keys is rejected and provider config values such as webhook URLs or tokens are not serialized into package artifacts. This config-leakage seam is now reused by webhook, presigned object-storage, and GitHub Release providers.

Step 43 execution record: WebhookExternalDeliveryProvider / HTTP JSON provider baseline is implemented. The default external delivery registry now includes `webhook` plus `webhook-json` / `http-webhook` aliases, and `reverse-agent-doctor --external-delivery-providers` reports it as `transport=webhook`, `supports_external_delivery=true`, and `review_only=false` without invoking provider factories. In dry-run, webhook delivery is side-effect-free and does not open a socket; in apply mode, it POSTs a JSON delivery package to the explicitly configured `webhook_url`. Result metadata records a redacted target URL, query / credential redaction booleans, request body digest and size, request attempt / success booleans, and response status code, while intentionally not recording request headers, response headers, or response body. Tests use a local HTTP server to prove apply sends JSON and headers while result artifacts do not serialize the query secret or header secret. This closes the first real network external delivery provider baseline; presigned object-storage and GitHub Release baselines are now also built in, while retry / overwrite policy and a fuller transaction state machine remain follow-ups.

Step 44 execution record: PresignedObjectExternalDeliveryProvider / object-storage PUT provider baseline is implemented. The default external delivery registry now includes `presigned-object` plus `object-storage` / `presigned-url` / `s3-presigned` aliases, and `reverse-agent-doctor --external-delivery-providers` reports it as `transport=object-storage`, `supports_external_delivery=true`, and `review_only=false` without invoking provider factories. In dry-run, presigned object delivery is side-effect-free and does not open a socket; in apply mode, it PUTs a JSON delivery package to the explicitly configured `presigned_url`. Result metadata records a redacted target URL, query / credential redaction booleans, object name, request body digest and size, request attempt / success booleans, content type, configured header count, and response status code, while intentionally not recording request headers, response headers, response body, URL query, URL credentials, or raw provider config values. Tests use a local HTTP server to prove apply sends JSON and configured headers while result artifacts do not serialize the query secret or header secret. GitHub Release JSON asset upload / explicit existing-release reuse / asset duplicate preflight baselines are now built in; asset overwrite is closed by Steps 66-67, retry/rate-limit metadata is closed by Step 68, and a fuller transaction state machine remains a follow-up.

Step 45 execution record: RuntimeBackend doctor / metadata CLI baseline is implemented. `RuntimeBackendRegistry` now exposes `list_registration_metadata()` so doctor can report canonical backend capabilities plus aliases and keys without constructing runtimes. `reverse-agent-doctor --runtime-backends` emits a side-effect-free `runtime_backend_matrix` with backend ids, aliases, target platforms, transport, capability flags, entry point group, summary counts, and side-effect policy. Metadata-only mode skips CDP port probes and does not invoke backend factories, start browser sessions, start Chrome, start MCP, or invoke platform tools such as ADB, simctl, or vendor devtools. Tests cover default core runtime metadata, entry point registration loading without factory invocation, and the registry metadata API.
Step 46 execution record: DeepAgents workspace manifest-only folder alias baseline is implemented. `workspace_contract.py` now exposes workspace route alias helpers, and backend artifact manifest entries for registered workspace artifacts include `metadata.workspace_alias` with the canonical flat path, authoritative-path flag, foldered future path, virtual URI, producer roles, and `migration_status=manifest-alias-only`. Web and platform-neutral pipelines keep writing the existing flat `workspace/*.json` canonical paths; this is a manifest compatibility alias baseline, not physical folder migration or dual-write.
Step 47 execution record: Delivery transaction state machine skeleton is implemented as a read-only evaluator and conservative transition planner. `reverse_deepagent.delivery.state_machine` exports `DeliveryTransactionState`, `DeliveryTransactionSnapshot`, `DeliveryTransitionPlan`, `evaluate_delivery_transaction_state(...)`, and `plan_delivery_transition(...)`; `DeliveryExecutionResult.to_dict()` now embeds `transaction_state` with current state, completed states, flags, evidence paths, blocking reasons, and recommended actions derived from result / journal / recovery / commit / external-delivery artifacts. This does not execute side effects, publish externally, recover manifests, or implement full cross-run rollback / idempotency hardening.

Step 48 execution record: BrowserProvider registry / entry-point discovery baseline is implemented. `reverse_deepagent.browser.registry` now exposes `BROWSER_PROVIDER_ENTRY_POINT_GROUP=reverse_deepagent.browser_providers`, `BrowserProviderRegistry.load_entry_points()`, `list_registration_metadata()`, built-in provider registration helpers, and `build_default_browser_provider_registry()`. The `native-web` runtime resolves `playwright-chromium`, `cloakbrowser`, `remote-cdp`, and aliases through the registry instead of hard-coded provider branches. `reverse-agent-doctor --browser-provider-matrix` now reports the entry point group, provider registration metadata, registered ids / aliases, and a metadata-only side-effect policy with `provider_factories_invoked=false`; it still does not probe CDP, launch browsers, call provider factories, or depend on MCP unless explicit smoke flags are used. Follow-ups now remain finer compatibility checks and real third-party BrowserProvider plugin implementations; `browser_runtime` subagent concretization is closed by Step 49, and the package template is closed by Step 50.

Step 49 execution record: Browser Runtime Subagent baseline is implemented. `reverse_deepagent.subagents.browser_runtime` now defines the `browser_runtime` DeepAgents subagent with a dedicated prompt and a BrowserProvider-facing tool boundary. The subagent exposes `list_browser_providers` and `describe_browser_provider` as metadata-only tools that report registry metadata, aliases, capability flags, and side-effect policy without launching browsers, probing CDP, invoking external provider factories, or using MCP. When a Web runtime is provided, the subagent also exposes `ensure_browser_session` for explicit session readiness checks; without a runtime it remains metadata-only. `build_reverse_agent(...)` inserts `browser_runtime` before `web_recon`, and the workspace contract now marks `browser_runtime` as implemented. `review` is closed by Step 53, `timeline` is closed by Step 54, and `debugger` is closed by Step 55, while all planned-contract subagent roles are now implemented. Follow-ups remain finer capability compatibility checks, real third-party BrowserProvider integrations; the package template itself is closed by Step 50 and planned-contract subagent extraction is closed by Step 57.

Step 50 execution record: BrowserProvider plugin package template is implemented. `packages/reverse-deepagent-browser-provider-template/` now provides a copy-and-replace optional package with a `reverse_deepagent.browser_providers` entry point named `template-browser`. Its registration returns non-secret `BrowserProviderCapabilities`, aliases, and a factory without launching browsers, probing CDP, invoking MCP, or calling the factory during metadata listing. The skeleton provider intentionally raises `BrowserProviderUnavailableError` from `start()` and `connect()` until an integrator replaces the lifecycle and session/page adapters. Tests cover the pyproject entry point, dependency declaration, metadata-only registration behavior, registry alias resolution, and explicit factory creation. Follow-ups remain real third-party BrowserProvider plugin implementations and future compatibility rule evolution for new provider capability flags.

Step 51 execution record: BrowserProvider capability compatibility matrix is implemented. `reverse_deepagent.browser.smoke` now exposes `validate_browser_provider_capability_compatibility(...)` and a `BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION`. Metadata-only browser provider matrices attach a `compatibility` object to each provider row, include compatibility counts in `summary`, and expose the rule version at the top level. The initial rules mark impossible combinations such as breakpoint support without CDP, persistent context without launch/connect lifecycle support, or response-body / request-initiator / WebSocket-frame capture without network events or CDP; suspicious runtime-eval, script-source, CDP, and managed-browser combinations produce warnings. The doctor browser-provider matrix now treats compatibility errors as not-ok while still preserving the no-factory, no-browser-start, no-CDP-probe, no-MCP side-effect boundary. Tests cover valid metadata, invalid capability combinations, matrix not-ok behavior, and doctor output.

Step 52 execution record: Delivery transaction inspector / doctor baseline is implemented as a read-only artifact inspection surface. `reverse_deepagent.delivery.inspector` exports `DELIVERY_TRANSACTION_INSPECTOR_VERSION`, `DELIVERY_TRANSACTION_ARTIFACT_NAMES`, `DeliveryTransactionInspection`, and `inspect_delivery_transaction_root(...)`; the inspector reads `delivery-transaction-journal.json`, `external-delivery-result.json`, `backend-artifact-manifest-recovery-preflight.json`, `backend-artifact-manifest-recovery.json`, and `backend-artifact-manifest-transaction-commit.json` from a delivery root, then reuses `evaluate_delivery_transaction_state(...)` and `plan_delivery_transition(...)` to emit `state_snapshot`, `transition_plan`, artifact load status, missing optional artifacts, load errors, and a read-only side-effect policy. `reverse-agent-doctor --delivery-transaction-root` exposes that inspection without starting Chrome, probing CDP, requiring MCP, invoking browser/runtime/external provider factories, mutating files, restoring manifests, committing transactions, or publishing externally. Tests cover journal-only local state, committed external-delivery state, malformed artifacts, and doctor metadata-only behavior. The recovery workflow executor baseline is implemented by Step 69. Follow-ups remain a write-capable cross-run rollback executor / physical state machine beyond the read-only rollback state baseline, stronger distributed transaction locking beyond the local transaction lock baseline, advanced adaptive provider retry policy, and third-party external delivery providers; GitHub Release explicit asset delete + replacement upload is implemented behind approval flags.

Step 53 execution record: Review Subagent baseline is implemented as a read-only DeepAgents review gate boundary. `reverse_deepagent.subagents.review` defines the `review` subagent, `prompts/review.txt` documents the no-delivery / no-approval boundary, and `tools.review_tools.make_evaluate_review_gate_tool()` exposes `evaluate_delivery_review_gate` for RebuildResult JSON plus optional EvidencePromotionResult JSON. The tool reuses `evaluate_review_gate(...)`, returns the normalized gate result and an explicit side-effect policy, and does not write artifacts, mutate files, execute local delivery, call external delivery providers, or record reviewer approvals. `build_reverse_agent(...)` now includes `review` by default, the coordinator prompt routes pre-delivery gate checks to it, and the workspace contract marks `review` as implemented; Step 54 marks `timeline` as implemented, Step 55 marks `debugger` as implemented, Step 56 marks `hook` as implemented, and Step 57 marks `rebuild` as implemented, leaving no planned-contract subagent roles. Tests cover pass / block gate behavior, pending stitch proposal blocking, side-effect policy, prompt loading, default agent subagent ordering, workspace contract status, and DeepAgents subagent smoke. Follow-ups remain the larger Browser/CDP, workspace migration, recovery, rollback, and external delivery provider items.

Step 54 execution record: Timeline Subagent baseline is implemented as a read-only DeepAgents flow-timeline review boundary. `reverse_deepagent.subagents.timeline` defines the `timeline` subagent, `prompts/timeline.txt` documents the no-materialization / no-approval / no-delivery boundary, and `tools.timeline_tools.make_review_flow_timeline_tool()` exposes `review_flow_timeline` for existing `flow-timeline.json` payloads. The tool summarizes entries, source counts, correlation group readiness, stitch candidates, stitch proposals, auto-stitch dry-runs, conflict resolutions, policy decisions, materialization plans / results, and rollback plan / result counts; it detects pending stitch proposals, blocked policy decisions, unresolved conflicts, and materialization requests without approval, then returns blockers, warnings, review-required items, next action, and an explicit read-only side-effect policy. `build_reverse_agent(...)` now includes `timeline` before `review`, the coordinator prompt routes flow timeline / stitch proposal checks to it before review gate evaluation, and the workspace contract marks `timeline` as implemented; Step 55 marks `debugger` as implemented, Step 56 marks `hook` as implemented, and Step 57 marks `rebuild` as implemented, leaving no planned-contract subagent roles. Tests cover pending-proposal blocking, approved timeline pass-through, side-effect policy, prompt loading, default agent ordering, workspace contract status, and DeepAgents subagent smoke.

Step 55 execution record: Debugger Subagent baseline is implemented as a read-only DeepAgents debugger artifact review boundary. `reverse_deepagent.subagents.debugger` defines the `debugger` subagent, `prompts/debugger.txt` documents the no-CDP-command / no-resume / no-step / no-evaluate boundary, and `tools.debugger_tools.make_review_debugger_artifacts_tool()` exposes `review_debugger_artifacts` for aggregated debugger artifact payloads. The tool summarizes debugger session status, paused status, continuation preflight status / source / requested action, live continuation availability, callframe counts, top callframes, callframe evaluations, mutation audit records, debugger actions, and debugger timeline event counts; it detects durable snapshot live-action blocking, debugger failures, unavailable paused sessions, missing artifacts, and paused sessions without callframes, then returns blockers, warnings, review-required items, next action, and an explicit read-only side-effect policy. `build_reverse_agent(...)` now includes `debugger` before `timeline`, and the workspace contract marks `debugger` as implemented; Step 56 marks `hook` as implemented and Step 57 marks `rebuild` as implemented, leaving no planned-contract subagent roles. Tests cover durable snapshot live resume blocking, live-available pass-through, missing artifact warning, side-effect policy, prompt loading, default agent ordering, workspace contract status, and DeepAgents subagent smoke.

Step 56 execution record: Hook Subagent baseline is implemented as a read-only DeepAgents hook artifact review boundary. `reverse_deepagent.subagents.hook` defines the `hook` subagent, `prompts/hook.txt` documents the no-install / no-JavaScript-eval / no-target-invoke boundary, and `tools.hook_tools.make_review_hook_artifacts_tool()` exposes `review_hook_artifacts` for aggregated hook artifact payloads. The tool summarizes installed function hooks, installed module hooks, source-logpoint counts, missing targets, hook candidates, function / module / generic hook timeline event counts, event type counts, and installed target paths; it detects hook failures, missing hook targets, installed hooks without captured events, and candidates without installed hooks, then returns blockers, warnings, review-required items, next action, and an explicit read-only side-effect policy. `build_reverse_agent(...)` now includes `hook` between `debugger` and `timeline`, and the workspace contract marks `hook` as implemented; Step 57 marks `rebuild` as implemented, leaving no planned-contract subagent roles. Tests cover installed-without-events warning, captured function and module events pass-through, failed hook blocking, side-effect policy, prompt loading, default agent ordering, workspace contract status, and DeepAgents subagent smoke.

Step 57 execution record: Rebuild Subagent split is implemented. `reverse_deepagent.subagents.rebuild` defines the `rebuild` subagent, `prompts/rebuild.txt` documents the generation / review boundary, and `tools.rebuild_tools.make_review_rebuild_artifacts_tool()` exposes `review_rebuild_artifacts` for RebuildResult / rebuild-plan payloads. The rebuild subagent owns `build_rebuild_delivery` plus read-only rebuild review; the delivery subagent is renamed to the `delivery` boundary and exposes `execute_local_delivery` plus the Step 65 `execute_delivery_transition` shell, keeping local delivery, backend manifest mutation, recovery, transaction commit, and external provider requests out of rebuild generation. `build_reverse_agent(...)` now orders `review -> rebuild -> delivery`, and the workspace contract marks `rebuild` as implemented, leaving no planned-contract subagent roles. Tests cover risk review hint blocking, ready bundle pass-through, not-ready warnings, delivery tool narrowing, prompt loading, default agent ordering, workspace contract status, and DeepAgents subagent smoke.

Step 58 execution record: WorkspacePathResolver / opt-in dual-write plan baseline is implemented. `reverse_deepagent.workspace_contract.WorkspacePathResolver` resolves registered workspace artifacts by artifact key, legacy `workspace/*.json` path, foldered future path, or `virtual://workspace/...` URI while keeping the legacy flat path authoritative by default. `WorkspacePathResolution` exposes canonical path / URI, future path / URI, read paths, write paths, producer roles, and migration status. Explicit `enable_dual_write=True` returns a plan-only write path tuple containing both legacy and future paths, but it does not create directories, copy files, move artifacts, or change pipeline write targets. `workspace_manifest_alias_metadata(...)` now includes `canonical_uri` and `resolver_migration_status=resolver-only`, and `workspace_contract_payload()` advertises resolver availability, dual-write opt-in, and physical migration disabled by default. Tests cover legacy-authoritative resolution, future path and virtual URI lookup, opt-in dual-write planning, payload policy, and existing Web / platform pipeline manifest alias compatibility. Physical folder migration and broader consumer adoption remain follow-ups; the opt-in actual dual-write writer baseline is closed by Step 59.

Step 59 execution record: Workspace opt-in actual dual-write writer baseline is implemented. `run_reverse_pipeline(...)`, `write_outputs(...)`, `run_platform_pipeline(...)`, and `write_platform_outputs(...)` now accept `enable_workspace_dual_write`, defaulting to `False` so legacy flat `workspace/*.json` writes remain unchanged. When explicitly enabled, registered workspace artifacts are written through `WorkspacePathResolver` to both the legacy canonical path and the foldered future path under the artifact root. A new `workspace_dual_write_plan` route writes `workspace/workspace-dual-write-plan.json` with artifact key, canonical path, future path, virtual URI, actual write paths, and migration boundary metadata. Backend artifact manifest entries still use legacy paths as canonical and expose foldered paths through alias metadata; the new audit artifact records physical dual-write output without moving existing files or changing authoritative paths. Tests cover default no-dual-write behavior, explicit future-path creation, audit plan contents, manifest canonical path stability, and existing Web / platform pipeline compatibility. Full physical folder migration and broader consumer adoption remain follow-ups.

Step 60 execution record: GitHubReleaseExternalDeliveryProvider baseline is implemented. The default external delivery registry now includes `github-release` plus `gh-release` / `github-release-assets` aliases, and `reverse-agent-doctor --external-delivery-providers` reports it as `transport=github-release`, `supports_external_delivery=true`, and `review_only=false` without invoking provider factories. In dry-run, GitHub Release delivery is side-effect-free and does not open a socket; in apply mode, it creates a GitHub release through the REST API and uploads a provider-neutral redacted JSON delivery package asset to the returned upload URL. Result metadata records redacted release / upload URLs, request body digest / size, request attempt / success flags, status codes, and secret-safe config summaries while intentionally not recording tokens, request headers, response headers, or response bodies. Duplicate external delivery guard still runs before provider factory / provider invocation. Explicit existing-release reuse is closed by Step 61, while asset overwrite/delete is closed by Steps 66-67, retry/rate-limit metadata is closed by Step 68, and advanced adaptive retry/backoff policy remains a follow-up.

Step 61 execution record: GitHub Release existing-release reuse baseline is implemented behind explicit `reuse_existing_release=true`. The default remains conservative: create-release failure does not automatically reuse an existing release. When explicitly enabled, create-release failure or missing upload URL triggers a GET to `/repos/{owner}/{repo}/releases/tags/{tag}`; if that lookup succeeds and returns an upload URL, the provider reuses that release and uploads the JSON asset. Metadata records `release_created`, `existing_release_lookup_attempted`, `existing_release_lookup_succeeded`, `existing_release_reused`, `existing_release_status_code`, and a redacted existing-release API URL without recording response bodies, response headers, request headers, or tokens. Capability metadata now exposes `supports_existing_release_reuse=true`. Same-name asset preflight is closed by Step 62, while asset overwrite/delete is closed by Steps 66-67, retry/rate-limit metadata is closed by Step 68, and advanced adaptive retry/backoff policy remains a follow-up.

Step 62 execution record: GitHub Release asset duplicate preflight baseline is implemented. `GitHubReleaseExternalDeliveryProvider` now checks existing release assets by default after release creation or explicit existing-release reuse succeeds. It reads the release `assets_url`, GETs the assets list, compares asset names against the configured `asset_name`, and blocks before upload if a same-name asset already exists. `allow_existing_asset=true` is an explicit override that only allows the upload attempt to continue; it does not delete or overwrite the existing asset and does not guarantee the GitHub API will accept the duplicate. Metadata records redacted `assets_url`, `asset_lookup_attempted`, `asset_lookup_succeeded`, `existing_asset_found`, `existing_asset_count`, `asset_lookup_status_code`, `check_existing_asset`, and `allow_existing_asset`, while still avoiding response body / header, request header, and token serialization. Capability metadata now exposes `supports_existing_asset_preflight=true`, `existing_asset_conflict_default=block`, and `supports_existing_asset_overwrite=false`. Tests cover create -> assets lookup -> upload, existing-release reuse -> assets lookup -> upload, default duplicate blocking, explicit duplicate upload attempt, registry metadata, doctor metadata, and secret redaction. Android / iOS / mini-program full runtime chains remain deferred.

Step 63 execution record: External delivery explicit retry policy baseline is implemented. `reverse_deepagent.delivery.executors` now exposes a provider-neutral `ExternalDeliveryHttpRequestResult` and `_http_request_with_retries(...)` helper used by the built-in webhook, presigned object-storage, and GitHub Release providers. Each provider supports `retry_attempts`, `retry_backoff_seconds`, and `retry_status_codes`, with `retry_attempts=0` by default so existing apply behavior still performs one request unless retry is explicitly configured. Apply metadata records `retry_enabled`, configured retry policy, attempt count, retry count, and secret-safe attempt summaries containing only attempt number, status code, error class, retryable, and will-retry flags. It still does not serialize request headers, response headers, response bodies, URL query secrets, or tokens, and dry-run remains side-effect-free. Registry / doctor capability metadata now reports `supports_explicit_retry=true`, `default_retry_attempts=0`, and default retry status codes for webhook, presigned object-storage, and GitHub Release. Tests cover webhook 503 -> retry -> 204 success plus registry and doctor metadata. Provider-specific Retry-After / rate-limit / jitter metadata is closed by Step 68; remaining follow-ups are advanced adaptive retry governors, stronger distributed transaction locking beyond the Step 75 local transaction lock baseline, and third-party delivery providers. Same-name asset overwrite/delete preflight planning is closed by Step 66 and explicit asset delete + replacement upload is closed by Step 67.

### Step 64 execution record: External delivery idempotency ledger baseline

Status: implemented as an append-only audit baseline.

`LocalDeliveryExecutor` now writes `external-delivery-idempotency-ledger.json` for explicit apply-mode external delivery attempts. The ledger records transaction id, idempotency key, provider id, result status, performed state, duplicate guard decisions, provider factory invocation evidence, blocking reasons, recommended actions, and secret-safe retry attempt summaries. Duplicate-guard-blocked retries append a ledger entry without invoking the provider factory. Dry-run remains side-effect free and does not write the ledger file.

The delivery journal exposes `external_delivery_idempotency_ledger_path`; the transaction state machine reports `external_delivery_idempotency_ledger_recorded` and an evidence path; the delivery transaction inspector reads the ledger artifact; the workspace contract indexes `workspace/external-delivery-idempotency-ledger.json` under `/workspace/delivery/`. This does not implement a recovery executor, remote overwrite policy, automatic retry, automatic rollback, or full cross-run transaction state machine.

### Step 65 execution record: Delivery transaction transition executor baseline

Status: implemented as an explicit transition shell, not a full automatic recovery state machine.

`reverse_deepagent.delivery.transitions` now provides `DeliveryTransactionTransitionExecutor`, `DeliveryTransitionExecutorConfig`, and `DeliveryTransitionExecution`. The executor inspects the current delivery transaction state, resolves a requested transition, validates conservative guards, and delegates the actual recovery / commit work to `LocalDeliveryExecutor` so existing digest, journal, rollback checkpoint, recovery preflight, and commit checks remain authoritative.

The supported transition set is intentionally narrow: `preflight_backend_manifest_recovery`, `apply_backend_manifest_recovery`, and `commit_cross_run_transaction`. Dry-run remains read-only. Apply mode requires an explicit transition instead of `auto`, so the executor will not automatically choose between recovery and commit when `plan_delivery_transition(...)` recommends the ambiguous `apply_recovery_or_commit_after_review` path.

The delivery subagent now exposes `execute_delivery_transition` alongside `execute_local_delivery`. Apply-mode transition attempts can write `delivery-transition-execution.json`; the delivery transaction inspector and workspace contract index this artifact under `/workspace/delivery/`. The baseline still does not implement automatic rollback, external delivery publication, remote release mutation, or a full cross-run transaction state machine.
### Step 66 execution record: GitHub Release asset overwrite/delete preflight plan baseline

Status: implemented as a preflight-plan-only baseline.

`GitHubReleaseExternalDeliveryProvider` now enriches successful same-name asset lookup results with a secret-safe `existing_asset` summary and an `existing_asset_overwrite_plan`. The plan records whether delete / overwrite would be required, that no delete or overwrite has been performed, the explicit approval requirements, and a partial-failure plan for delete-succeeds-upload-fails / delete-fails / upload-conflict-after-delete cases. `allow_existing_asset=true` still only allows a duplicate upload attempt and does not execute overwrite semantics.

The plan is intentionally side-effect constrained: it does not send GitHub DELETE requests, does not overwrite existing assets, does not record response bodies, request / response headers, tokens, URL query secrets, or browser download URL paths. Registry and doctor metadata expose `supports_existing_asset_overwrite_preflight=true` and `supports_existing_asset_delete_preflight=true` while keeping `supports_existing_asset_overwrite=false` and `supports_existing_asset_delete=false`. Tests cover default duplicate blocking with plan creation, explicit duplicate upload attempt without delete, registry metadata, doctor metadata, and secret redaction. True GitHub asset delete + replacement upload is closed by Step 67; advanced adaptive retry / secondary rate-limit policy remains a follow-up.
### Step 67 execution record: GitHub Release explicit asset delete + replacement upload baseline

Status: implemented as an explicit-approval external delivery baseline.

`GitHubReleaseExternalDeliveryProvider` can now execute the overwrite plan generated in Step 66. When a same-name asset is found, the provider sends DELETE only if `approve_existing_asset_delete=true` and `approve_replacement_upload=true` are both configured, the looked-up asset name matches, the optional `expected_existing_asset_id` matches the looked-up asset id, and the asset API URL has a supported HTTP scheme. DELETE success is required before replacement upload; DELETE failure, identity mismatch, missing delete URL, or missing approvals block the upload.

The external delivery result records delete approval state, expected asset id configuration, identity match, delete request attempts, delete status, delete performed, overwrite performed, replacement upload attempt, and the updated overwrite plan. Metadata remains secret-safe: tokens, request / response headers, response bodies, URL query secrets, and browser download URL paths are not serialized. Registry and doctor metadata now expose `supports_existing_asset_overwrite=true`, `supports_existing_asset_delete=true`, and `existing_asset_overwrite_requires_explicit_approval=true`. Tests cover successful delete + upload, id mismatch blocking, delete failure without upload, default duplicate blocking, explicit duplicate upload without delete, registry metadata, doctor metadata, and secret redaction. Advanced adaptive retry / secondary rate-limit policy and full transaction recovery remain follow-ups.
### Step 68 execution record: Provider-specific retry / rate-limit metadata baseline

Status: implemented as a secret-safe metadata hardening baseline, not an adaptive retry governor.

`WebhookExternalDeliveryProvider`, `PresignedObjectExternalDeliveryProvider`, and `GitHubReleaseExternalDeliveryProvider` now accept `retry_jitter_seconds` and `honor_retry_after` alongside the existing explicit retry config. Defaults remain conservative: `retry_attempts=0`, `retry_backoff_seconds=0`, and `retry_jitter_seconds=0`, so dry-run remains side-effect-free and apply mode does not add implicit retries or sleeps unless retry/backoff is explicitly configured.

`_http_request_with_retries(...)` now parses `Retry-After` and GitHub-compatible `X-RateLimit-*` response headers into per-attempt metadata. Provider results expose stage-level retry summaries for webhook/presigned requests and GitHub release/create, existing-release lookup, asset lookup, existing-asset delete, and upload stages. The idempotency ledger preserves the same safe attempt fields: retry-after seconds, seen/honored flags, planned delay, jitter config, retry budget exhaustion, and sanitized rate-limit counters. Raw request headers, response headers, response bodies, tokens, URL query secrets, and browser download URLs are still not serialized.

Registry and doctor capability metadata now report `supports_retry_after_metadata=true`, `supports_rate_limit_metadata=true`, `supports_retry_budget_metadata=true`, `supports_retry_jitter_config=true`, and `default_retry_jitter_seconds=0` for webhook, presigned object-storage, and GitHub Release providers. Tests cover webhook Retry-After / rate-limit metadata, GitHub Release 429 -> retry -> 201 metadata, registry metadata, doctor metadata, ledger redaction, and secret redaction. Advanced adaptive retry budgets, GitHub secondary rate-limit policy, full transaction recovery, and third-party external delivery providers remain follow-ups.

### Step 69 execution record: Delivery transaction recovery workflow executor baseline

Status: implemented as an explicit-review-only recovery workflow executor, not a cross-run rollback state machine.

`reverse_deepagent.delivery.recovery` now provides `DeliveryTransactionRecoveryExecutor`, `DeliveryRecoveryExecutorConfig`, `DeliveryRecoveryExecution`, and `SUPPORTED_DELIVERY_RECOVERY_ACTIONS`. The executor sits one level above the Step 65 transition shell: it inspects the delivery root, builds a recovery workflow plan, and can orchestrate `preflight_backend_manifest_recovery` followed by `apply_backend_manifest_recovery` through the existing transition executor. Low-level journal, source digest, rollback checkpoint, recovery preflight, and manifest mutation checks remain delegated to `LocalDeliveryExecutor`.

Supported actions are `plan_recovery`, `preflight_recovery`, and `apply_recovery`. Defaults remain dry-run and read-only. Apply-mode recovery requires `approve_recovery=true` plus an `expected_transaction_id`; otherwise the executor blocks before running transitions. Successful apply-mode workflows write `delivery-recovery-execution.json`; internal transition records are suppressed so the recovery workflow has one authoritative audit artifact. The side-effect policy records manifest recovery while keeping external delivery, publishing, and cross-run transaction commit disabled.

The delivery subagent now exposes `execute_delivery_recovery` alongside `execute_local_delivery` and `execute_delivery_transition`, and the workspace contract indexes `workspace/delivery-recovery-execution.json` under `/workspace/delivery/`. Tests cover dry-run planning, approval blocking, preflight -> recovery orchestration, tool invocation, subagent exposure, and workspace contract routing. Remaining follow-ups are the write-capable cross-run rollback executor / physical state machine beyond the read-only rollback state baseline, stronger distributed transaction locking beyond the local transaction lock baseline, third-party external delivery providers, and advanced browser/debugger capabilities.


### Step 70 execution record: Delivery transaction idempotency guard baseline

Status: implemented as a local terminal-action duplicate guard, not a distributed transaction lock.

`LocalDeliveryExecutor` now exposes `DeliveryTransactionIdempotencyGuard` and writes `delivery-transaction-idempotency-guard.json` when an apply-mode duplicate attempts to repeat an already completed backend manifest recovery or cross-run transaction commit. The guard is triggered when the journal already records `backend_manifest_recovered=true` / `cross_run_transaction_committed=true` or the existing terminal artifact is already successful. In that case the duplicate action is blocked and the existing `backend-artifact-manifest-recovery.json` or `backend-artifact-manifest-transaction-commit.json` is preserved rather than overwritten by a blocked record.

`DeliveryExecutionResult.to_dict()` includes `transaction_idempotency_guard`, and the workspace contract indexes `workspace/delivery-transaction-idempotency-guard.json` under `/workspace/delivery/`. Tests cover duplicate recovery and duplicate commit preservation, plus focused delivery state/tool/inspector compatibility. Remaining follow-ups are a write-capable cross-run rollback executor / physical state machine beyond the read-only rollback state baseline, stronger distributed transaction locking / resume semantics, advanced adaptive retry policy, and third-party external delivery providers. Android / iOS / mini-program full runtime chains remain deferred.


### Step 71 execution record: Delivery cross-run rollback state machine baseline

Status: implemented as a read-only cross-run rollback workflow state machine, not a write-capable rollback executor.

`reverse_deepagent.delivery.rollback_state` now provides `DeliveryRollbackPhase`, `DeliveryRollbackTransition`, `DeliveryRollbackState`, and `evaluate_delivery_rollback_state(...)`. The evaluator reads the same standard delivery artifact payloads as the transaction state machine and derives a rollback workflow phase: `no_transaction`, `local_delivery_applied`, `rollback_preflight_required`, `rollback_decision_required`, `rollback_applied`, `committed`, `external_delivery_performed`, `duplicate_terminal_action_blocked`, or `blocked`. It emits checks, blocking reasons, evidence paths, flags, a conservative recommended action, and review-gated allowed transitions without mutating files, restoring manifests, committing transactions, publishing externally, or acquiring distributed locks.

The delivery inspector now includes `rollback_state`, so doctor-style inspection can show whether a delivery root needs recovery preflight, reviewer choice between recovery and commit, post-recovery review, duplicate terminal action review, or external-delivery guard handling. The workspace contract indexes `workspace/delivery-rollback-state.json` under `/workspace/delivery/`, and the public delivery API exports the rollback state types and evaluator. Tests cover mutated-manifest preflight requirement, reviewer decision after recovery preflight, recovered manifest phase, committed phase, duplicate terminal guard, and inspector rollback state projection. Remaining follow-ups are a write-capable cross-run rollback executor / physical state machine, stronger distributed transaction locking and resume semantics, advanced adaptive retry policy, and third-party external delivery providers. Android / iOS / mini-program full runtime chains remain deferred.

### Step 72 execution record: Delivery rollback state artifact writer baseline

Status: implemented as an explicit audit-artifact writer, not a physical rollback executor.

`reverse_deepagent.delivery.rollback_writer` now exposes `DeliveryRollbackStateArtifactWriter`, `DeliveryRollbackStateWriterConfig`, and `DeliveryRollbackStateWrite`. The writer reuses the delivery transaction inspector, embeds the current read-only `rollback_state`, and writes `delivery-rollback-state.json` only when explicitly run with `mode=apply` and no artifact load errors are present. Dry-run remains read-only and returns the same durable-state plan without creating the delivery root.

The delivery subagent exposes `write_delivery_rollback_state` alongside `execute_local_delivery`, `execute_delivery_transition`, and `execute_delivery_recovery`. The tool is constrained to writing the rollback-state audit artifact only: it does not restore manifests, commit transactions, call external delivery providers, acquire distributed locks, publish externally, or execute physical rollback. Tests cover dry-run behavior, apply-mode artifact writing, tool invocation, subagent exposure, and workspace route metadata. Remaining follow-ups are a write-capable cross-run rollback executor / physical state machine, stronger distributed transaction locking and resume semantics, advanced adaptive retry policy, and third-party external delivery providers. Android / iOS / mini-program full runtime chains remain deferred.

### Step 73 execution record: Delivery rollback executor dry-run / preflight baseline

Status: implemented as a plan / preflight rollback executor baseline, not a rollback apply or physical state machine.

`reverse_deepagent.delivery.rollback` now exposes `DeliveryRollbackExecutor`, `DeliveryRollbackExecutorConfig`, `DeliveryRollbackExecution`, and `SUPPORTED_DELIVERY_ROLLBACK_ACTIONS`. The executor supports `plan_rollback` and `preflight_rollback`. Dry-run is read-only. Explicit apply-mode `preflight_rollback` writes the durable rollback-state artifact, delegates to the transition executor to write `backend-artifact-manifest-recovery-preflight.json`, and records `delivery-rollback-execution.json`.

The delivery subagent exposes `execute_delivery_rollback`, and the workspace contract indexes `workspace/delivery-rollback-execution.json` under `/workspace/delivery/`. Safety gates block malformed artifacts, terminal rollback states, external-delivery-performed states, duplicate terminal guards, missing expected transaction ids, and missing backend manifest paths for apply preflight. The executor still does not apply recovery, restore manifests, commit transactions, publish external delivery, acquire distributed locks, execute physical rollback, or implement resume semantics. Remaining follow-ups are rollback apply / physical state machine, stronger distributed transaction locking and resume semantics, advanced adaptive retry policy, and third-party external delivery providers. Android / iOS / mini-program full runtime chains remain deferred.

### Step 74 execution record: Delivery rollback apply executor explicit-review-only baseline

Status: implemented as an explicit-review-only local backend-manifest rollback baseline, not a broader physical rollback state machine.

`reverse_deepagent.delivery.rollback` now includes `apply_rollback` in `SUPPORTED_DELIVERY_ROLLBACK_ACTIONS`. `DeliveryRollbackExecutorConfig` accepts `approve_rollback` and `expected_rollback_phase`, and apply mode gates rollback on the `rollback_decision_required` phase by default, explicit approval, an expected transaction id, and a backend manifest path. When those gates pass, the rollback executor delegates to `DeliveryTransactionRecoveryExecutor(action=apply_recovery)` so the existing recovery preflight and digest checks remain authoritative.

Successful `apply_rollback` writes the rollback-state audit artifact, restores the local backend manifest from the rollback checkpoint through the recovery executor, writes `backend-artifact-manifest-recovery.json`, and records `delivery-rollback-execution.json` with `status=rolled_back`. The side-effect policy marks `manifest_recovered=true`, `local_manifest_rollback_performed=true`, and `files_mutated=true`, while keeping `transaction_committed=false`, `external_delivery_performed=false`, `physical_rollback_performed=false`, `broader_filesystem_physical_rollback_performed=false`, and `distributed_lock_acquired=false`.

Tests cover blocked apply without explicit approval, approved manifest recovery, tool invocation, rollback phase transition to `rollback_applied`, and preservation of the no-commit / no-external-delivery boundary. Remaining follow-ups are a broader physical rollback state machine, stronger distributed transaction locking and resume semantics, advanced adaptive retry policy, and third-party external delivery providers. Android / iOS / mini-program full runtime chains remain deferred.

### Step 75 execution record: Delivery transaction lock / resume preflight baseline

Status: implemented as an opt-in local delivery-root lock / resume preflight baseline, not a distributed transaction lock or full durable resume workflow.

`LocalDeliveryExecutor` now exposes `DeliveryTransactionLock` and accepts `require_transaction_lock`, `transaction_lock_owner`, `transaction_lock_lease_seconds`, and `expected_resume_token`. When explicitly enabled for apply-mode side-effect operations, the executor writes or checks `delivery-transaction-lock.json` before local artifact delivery apply, backend manifest in-place mutation, backend manifest recovery apply, cross-run transaction commit, and external delivery requests. The lock artifact records the operation, owner, lease expiry, resume token, expected resume token, existing lock evidence, checks, blocking reasons, and recommended actions. Same-owner execution or a matching resume token can continue; another owner, mismatched resume token, malformed lock, or stale lock blocks and requires manual review / cleanup. Stale locks are detected but not automatically taken over.

The lock gate is side-effect-protecting: when blocked, the result remains `status=blocked` with `next_action=review_or_release_delivery_transaction_lock`, and downstream helpers run with effective dry-run semantics. Blocked locks do not copy artifacts, mutate backend manifests, restore manifests, commit transactions, call external delivery providers, write receipt / journal / recovery / commit / external-delivery result artifacts, or overwrite the existing lock. Transition, recovery, rollback, and delivery tool wrappers now pass through the lock parameters. The delivery inspector indexes `delivery-transaction-lock.json`, and the workspace contract exposes `workspace/delivery-transaction-lock.json` under `/workspace/delivery/`.

Tests cover local lock acquire / block / resume, lock blocking preserving an existing owner lock, lock blocking preventing backend manifest in-place mutation and terminal artifact writes, delivery tool lock parameter pass-through, inspector load status, and workspace route metadata. Remaining follow-ups are a true distributed transaction lock with lease renewal / fencing / release semantics, a durable resume workflow beyond the local audit token, a broader physical rollback state machine, advanced adaptive provider retry policy, and more third-party external delivery providers. Android / iOS / mini-program full runtime chains remain deferred.

### Step 76 execution record: Delivery transaction lock release / stale review baseline

Status: implemented as an explicit local delivery-root lock cleanup / stale review baseline, not a distributed lock release or durable resume workflow.

`LocalDeliveryExecutor` now accepts `release_transaction_lock`, `approve_transaction_lock_release`, `expected_transaction_lock_owner`, and `expected_transaction_lock_transaction_id`. Dry-run returns a release plan. Apply mode writes `delivery-transaction-lock-release.json` and removes `delivery-transaction-lock.json` only when explicit approval is present and optional owner / transaction id / resume token checks match the existing lock. Missing locks are reported as `no_lock_found`; malformed locks, approval gaps, owner mismatch, transaction id mismatch, and resume-token mismatch block without deleting the lock. Stale locks are detected and recorded but are not automatically taken over.

The local delivery tool exposes the release parameters, the delivery inspector indexes the release artifact without exposing its full payload, and the workspace contract maps `workspace/delivery-transaction-lock-release.json` into `/workspace/delivery/`. The boundary remains local-file cleanup only: no distributed consensus, no lease renewal, no fencing token, no automatic stale takeover, and no full durable resume workflow scheduler. Tests cover approval blocking, approved release, expected-owner mismatch, tool invocation, inspector load status, and workspace route metadata. Android / iOS / mini-program full runtime chains remain deferred.

### Step 77：Durable delivery resume planner baseline

Status: implemented as a planner / audit-artifact writer, not a resume runner.

`delivery.resume` adds `DeliveryResumePlanner`, `DeliveryResumePlannerConfig`, `DeliveryResumePlan`, and `SUPPORTED_DELIVERY_RESUME_ACTIONS`. It reads existing delivery transaction artifacts through the inspector, summarizes transaction state, rollback state, transition recommendations, local transaction lock / release evidence, and emits a machine-readable `recommended_resume_action`, `resume_steps`, checks, blockers, and lock summary. In dry-run it is read-only; in apply mode it writes only `delivery-resume-plan.json` when checks pass. The delivery subagent exposes `plan_delivery_resume`, the inspector indexes `delivery-resume-plan.json`, and the workspace contract maps `workspace/delivery-resume-plan.json` to `/workspace/delivery/delivery-resume-plan.json`.

Boundary: this is not a full durable resume workflow scheduler. It does not execute transitions, restore manifests, commit transactions, publish external delivery, acquire or release distributed locks, take over stale locks, or perform physical rollback. Remaining follow-ups are full durable resume workflow scheduling, true distributed transaction locking, broader physical rollback state machine, advanced adaptive provider retry policy, and third-party external delivery providers. Android / iOS / mini-program full runtime chains remain deferred.


### Step 78 execution record: Review approval ledger baseline

Status: implemented as an approval-audit-only review ledger, not a delivery, rollback, materialization, or automatic approval executor.

`reverse_deepagent.review_approval` adds `ReviewApprovalConfig`, `ReviewApprovalRecord`, `ReviewApprovalLedgerWriter`, `SUPPORTED_REVIEW_APPROVAL_MODES`, `SUPPORTED_REVIEW_APPROVAL_DECISIONS`, and `SUPPORTED_REVIEW_APPROVAL_ACTIONS`. Dry-run remains read-only. Apply mode writes `review-approval-record.json` and appends to `review-approval-ledger.json` only when the reviewer is present, the decision and mode are supported, `approve_decision_record=true`, and optional subject digest expectations match. Blocked attempts do not write either artifact.

The review subagent now exposes `record_review_approval` alongside the read-only `evaluate_delivery_review_gate` tool. The new tool defaults to `artifact_root/workspace`, accepts optional metadata JSON, and returns an explicit side-effect policy showing that delivery, rollback, manifest mutation, transaction commit, external delivery, materialization, and automatic approval are not performed. The workspace contract maps `workspace/review-approval-record.json` and `workspace/review-approval-ledger.json` into `/workspace/review/`. Tests cover the ledger writer, tool invocation, subagent exposure, and workspace route metadata. Android / iOS / mini-program full runtime chains remain deferred.


### Step 79 execution record: Delivery resume runner baseline

Status: implemented as a review-gated single-transition resume runner, not a full durable workflow scheduler.

`reverse_deepagent.delivery.resume_runner` adds `DeliveryResumeRunner`, `DeliveryResumeRunnerConfig`, `DeliveryResumeExecution`, and `SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS`. The runner reuses `DeliveryResumePlanner` for current state and lock preflight, then requires a matching `review-approval-ledger.json` entry before apply-mode execution. Supported runner actions are `plan_only`, `preflight_backend_manifest_recovery`, `apply_backend_manifest_recovery`, and `commit_cross_run_transaction`. Dry-run remains read-only and may run transition dry-runs without approval.

The delivery subagent now exposes `execute_delivery_resume` after `plan_delivery_resume`. Apply mode delegates exactly one explicit transition to `DeliveryTransactionTransitionExecutor`, preserving the existing LocalDeliveryExecutor journal, digest, recovery, commit, and lock checks. Successful apply runs write `delivery-resume-execution.json`, and the workspace contract maps `workspace/delivery-resume-execution.json` into `/workspace/delivery/`. The runner does not start a new local delivery, choose ambiguous rollback-vs-commit paths, publish external delivery, release/acquire distributed locks, take over stale locks, or execute broader physical rollback. Android / iOS / mini-program full runtime chains remain deferred.

### Step 80 execution record: Delivery transaction lock provider contract baseline

Status: implemented as a pluggable provider contract plus local filesystem reference provider, not a true distributed consensus lock.

`reverse_deepagent.delivery.lock_provider` now provides `DeliveryTransactionLockProvider`, `DeliveryTransactionLockProviderConfig`, `DeliveryTransactionLockOperation`, `DeliveryTransactionLockProviderRegistry`, `DeliveryTransactionLockProviderRegistration`, `DeliveryTransactionLockProviderCapabilities`, `LocalFileDeliveryTransactionLockProvider`, `build_default_delivery_transaction_lock_provider_registry(...)`, and `manage_delivery_transaction_lock(...)`. The registry owns the `reverse_deepagent.delivery_lock_providers` entry point group, and the built-in `local-file-lock` provider also exposes `filesystem-lock` / `local-distributed-lock` aliases.

The delivery subagent now exposes `manage_delivery_transaction_lock_provider` after `execute_delivery_resume`. The tool supports `inspect_lock`, `acquire_lock`, `renew_lock`, and `release_lock`; dry-run remains read-only, while explicit apply writes `delivery-distributed-transaction-lock.json` and `delivery-distributed-transaction-lock-operation.json` through the local reference provider. The workspace contract maps both artifacts into `/workspace/delivery/`, and tests cover provider registry metadata, dry-run read-only behavior, acquire / renew / blocked acquire / approved release semantics, tool invocation, subagent exposure, and workspace routes.

Boundary: this is a stable provider seam and local-file reference implementation. It does not replace the existing LocalDeliveryExecutor `delivery-transaction-lock.json` gate, does not contact Redis / etcd / DB / object storage, does not provide cross-machine consensus, does not start delivery, does not publish external delivery, does not mutate manifests, does not commit transactions, and does not take over stale locks automatically. Remaining follow-ups are real external distributed lock providers, lease renewal loops, downstream fencing-token enforcement, durable resume scheduling beyond the local workflow-journal baseline such as daemon / distributed orchestration, broader physical rollback state machine, advanced adaptive provider retry policy, and more third-party external delivery providers. Android / iOS / mini-program full runtime chains remain deferred.

### Step 81 execution record: Delivery resume workflow scheduler baseline

Status: implemented as a review-gated local durable workflow journal, not a timer daemon or distributed workflow engine.

`reverse_deepagent.delivery.resume_scheduler` adds `DeliveryResumeWorkflowScheduler`, `DeliveryResumeWorkflowSchedulerConfig`, `DeliveryResumeWorkflowExecution`, `SUPPORTED_DELIVERY_RESUME_WORKFLOW_ACTIONS`, and `SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS`. Supported workflow actions are `plan_workflow` and `execute_workflow`. Supported step actions are `preflight_backend_manifest_recovery`, `apply_backend_manifest_recovery`, and `commit_cross_run_transaction`; each executable step delegates to `DeliveryResumeRunner`, preserving the existing transition executor, LocalDeliveryExecutor digest checks, journal checks, transaction lock gates, idempotency guards, and review approval semantics.

The delivery subagent now exposes `execute_delivery_resume_workflow` between `execute_delivery_resume` and `manage_delivery_transaction_lock_provider`. Dry-run remains read-only. Apply mode requires matching `review-approval-ledger.json` entries for every pending step, writes `delivery-resume-workflow.json`, appends successful steps to `delivery-resume-workflow-journal.json`, and skips step actions already recorded as completed in the local workflow journal. The workspace contract maps both new artifacts into `/workspace/delivery/`.

Boundary: this is a local delivery root resume-of-resume scheduler baseline. It does not run in the background, poll on a timer, coordinate across machines, acquire or release distributed locks, start a new local delivery, publish external delivery, automatically choose rollback versus commit, execute broader physical rollback, or replace the existing review approval gates. Android / iOS / mini-program full runtime chains remain deferred.

### Step 82 execution record: ExternalDeliveryProvider plugin package template

Status: implemented as a copy-and-replace optional package template, not a real cloud / release-system provider.

`packages/reverse-deepagent-external-delivery-provider-template/` now declares the `reverse_deepagent.external_delivery_providers` entry point and exposes `template-external-delivery = reverse_deepagent_external_delivery_provider_template:external_delivery_provider_registration`. The registration returns non-secret `ExternalDeliveryProviderCapabilities`, aliases, and a factory without invoking that factory during metadata loading. The template package does not import cloud SDKs, open sockets, read credentials, upload artifacts, or publish releases from registration / metadata paths.

`TemplateExternalDeliveryProvider.deliver()` is intentionally publication-disabled. Dry-run returns a reviewable `planned` result for a valid local delivery package; apply mode returns a structured `blocked` result with `external_delivery_performed=false` until an integrator replaces `deliver()` with real SDK / HTTP delivery logic. The template README documents the required side-effect boundaries: preserve dry-run side-effect freedom, keep metadata non-secret, retain core duplicate-guard / idempotency / review-gate semantics, and never serialize tokens, presigned URLs, raw headers, response bodies, or credentials.

Tests cover the pyproject entry point, dependency declaration, side-effect-free registration metadata, explicit factory invocation, registry alias resolution, dry-run plan behavior, apply blocking behavior, and the no-publication boundary. Remaining follow-ups are real third-party providers such as S3 / OSS / GCS / GitLab Release / internal release systems, plus advanced adaptive retry / secondary rate-limit policies. Android / iOS / mini-program full runtime chains remain deferred.

### Step 83 execution record: SQLite delivery transaction lock provider baseline

Status: implemented as a local SQLite transactional lock provider baseline, not a Redis / etcd / database consensus lock.

`reverse_deepagent.delivery.lock_provider` now includes `SQLiteDeliveryTransactionLockProvider` and `sqlite_delivery_transaction_lock_provider_registration()`. The default delivery transaction lock provider registry registers `sqlite-lock` with `db-lock`, `sqlite-transaction-lock`, and `local-db-lock` aliases alongside the existing `local-file-lock` reference provider. Registration and metadata listing remain side-effect-light and do not open network sockets, read credentials, start browsers, or invoke external services.

The SQLite provider stores the authoritative lock row in `delivery-distributed-transaction-lock.sqlite3` under `delivery_transaction_locks`, using `BEGIN IMMEDIATE` for serialized local write transactions. Apply-mode acquire / renew writes the SQLite row and continues to emit `delivery-distributed-transaction-lock.json` as a JSON projection plus `delivery-distributed-transaction-lock-operation.json` as an audit record. Apply-mode release deletes the SQLite row and removes the JSON projection after the existing release approval checks pass. Dry-run remains read-only.

The provider reuses the existing lock contract semantics: expected owner checks, expected fencing token checks, explicit release approval, stale takeover gate, lease timestamps, fencing-token increments, structured blockers, recommended actions, and side-effect policy. Its metadata marks `provider_transport=sqlite`, `coordination_scope=local-sqlite-transaction`, `sqlite_transactional_storage=true`, and `supports_distributed_consensus=false`.

Boundary: this is stronger than the JSON-file reference for same-host / same-database writer serialization, but it is still not cross-machine consensus. It does not contact Redis, etcd, Postgres, MySQL, object storage, or cloud services; it does not replace the existing LocalDeliveryExecutor `delivery-transaction-lock.json` gate; it does not automatically renew leases, take over stale locks, execute delivery, publish external delivery, mutate manifests, commit transactions, or enforce downstream fencing tokens. Remaining follow-ups are real external distributed lock providers, lease renewal loops, downstream fencing-token enforcement, durable resume scheduling beyond the local workflow journal, broader physical rollback, advanced adaptive retry, and real third-party delivery providers. Android / iOS / mini-program full runtime chains remain deferred.

Tests cover default registry metadata, alias resolution, SQLite acquire / renew / release storage updates, JSON projection and operation record emission, and tool invocation through the `db-lock` alias.
