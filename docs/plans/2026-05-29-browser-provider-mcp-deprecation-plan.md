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

Status: hook baseline, WebSocket send/message capture, target-function wrapper baseline, webpack-like module export hook baseline, module discovery baseline with script inventory, read-only `require.c` / `require.m` runtime cache introspection, and explicit custom object runtime / module federation exposed-module function-path candidates, source-level logpoint baseline with bundle offset, Source Map exact, GLB bias, sourceRoot, and indexed section remap support, provider-neutral BreakpointManager baseline, in-process paused-session registry baseline, paused-session continuation preflight, durable paused-session snapshot inspect-only baseline, native-web runtime-eval candidate validation, basic paused/callframe breakpoint smoke, explicit evaluateOnCallFrame baseline, callframe evaluation policy baseline, callframe mutation audit baseline, closure-scope function discovery baseline, page-level coarse mutation audit baseline, MutationObserver timeline baseline around an explicit trigger, debugger step-control baseline, single-run debugger timeline baseline, native-web recon flow timeline baseline, explicit flow timeline continuation baseline, conservative flow timeline correlation hints, conservative flow timeline correlation groups, group verification readiness, manual stitch candidates, review-gated stitch proposals, evidence-promotion review requirement extraction, review gate blocking for pending stitch proposals, reviewer-approved stitched-flow materialization baseline, and auto-stitch dry-run scoring records, conservative policy decision gates, plan-only materialization plans, explicit-review-only auto-stitch materialization results, and materialization audit / rollback-plan baselines, review-only auto-stitch conflict resolution records, transaction-log-only materialization transaction records, dry-run / explicit-review-only rollback execution records, post-rollback review gate recompute baseline records, physical rollback dry-run diff records, explicit-review-only physical rollback mutation records, and post-physical-rollback review gate rerun records, standard review gate replacement records, post-replacement delivery guard rerun records, and artifact-model final delivery package records, explicit-review-only transaction commit record baselines, and local delivery executor contract baseline and backend artifact manifest mutation policy baseline plus backend manifest in-place mutation preflight baseline plus explicit-review-only backend manifest in-place mutation executor baseline and cross-run recovery preflight baseline for manual stitch candidates are implemented and tested locally. Cross-process live CDP paused execution continuation, arbitrary custom loader traversal / async chunk graph / execution-style module federation analysis, automatic wrapper hooks for arbitrary closure-internal functions beyond the paused-callframe evidence baseline, source-map name resolution / complex URL semantics / complex indexed section semantics, JS heap fine-grained mutation auditing, object graph diff, and automatic full cross-request timeline materialization without explicit review approval, full conflict resolver state-machine integration, cross-run physical rollback transaction state machine, cross-run transaction idempotency hardening, external delivery executor beyond the local-filesystem commit baseline and cross-run manifest recovery state machine remain future debugger-scope work; native-web recon writes `flow-timeline.json` from baseline collector fragments, annotates entries with request / URL / method / initiator / hook / candidate correlation hints, derives `correlation_groups` for shared hints, and marks each group with `verification.status`, evidence booleans, and `missing_for_ready`, promotes reviewable groups into manual-only `stitch_candidates`, scores those candidates through dry-run-only `auto_stitch_dry_runs` with `confidence_score`, `score_reasons`, `conflict_reasons`, `review_required=true`, `would_materialize=false`, and `automatic_stitching=false`, evaluates `auto_stitch_policy_decisions` / `auto_stitch_policy_summary` as a conservative review-gate decision layer, produces plan-only `auto_stitch_materialization_plans` / `auto_stitch_materialization_summary` for policy-eligible decisions without writing artifacts, materializes only explicitly approved `auto_stitch_materialization_review_decisions` into `auto_stitch_materialization_results` and reviewer-approved `stitched-flow.json` baselines with `automatic_stitching=false`, emits `auto_stitch_materialization_audit_entries` and `auto_stitch_materialization_rollback_plans` with `automatic_rollback=false`, produces dry-run `auto_stitch_rollback_execution_plans`, records only explicitly approved logical rollback results without mutating `stitched-flow.json`, emits blocking `auto_stitch_rollback_review_gate_recomputations` that do not replace the standard review gate, emits dry-run `auto_stitch_physical_rollback_dry_run_diffs` that describe would-remove / manifest impact, applies explicitly approved `auto_stitch_physical_rollback_review_decisions` into `auto_stitch_physical_rollback_results` by removing matching entries from the current `stitched_flows` artifact model, emits blocking `auto_stitch_post_physical_rollback_review_gate_reruns` without replacing the standard review gate, records explicitly approved `auto_stitch_standard_review_gate_replacement_results`, emits `auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns`, emits artifact-model `auto_stitch_post_standard_review_gate_replacement_final_delivery_packages`, records explicit-review-only `auto_stitch_transaction_commit_results`, promotes only `ready_for_manual_stitch_review` candidates into pending-review `stitch_proposals`, surfaces those pending proposals as evidence-level review requirements, blocks delivery through `review-gate.json` with `review_stitch_proposals_before_delivery`, materializes explicitly approved proposals as `stitched-flow.json` with `automatic_stitching=false`, and keeps explicit `flow-timeline` continuation as a source-fragment normalization baseline rather than automatic stitching.

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
- Target-function hook baseline is limited to globally reachable paths such as `window.buildSign`; module discovery baseline is limited to best-effort source inventory extraction, read-only webpack-like `require.c` / `require.m` runtime cache and registry introspection, and explicit custom object runtime / module federation exposed-module snapshots that produce function-path candidates; it still does not traverse arbitrary custom loaders, async chunk graphs, or execute federation `get/init` flows; source-level logpoint baseline can remap generated offsets and Source Map v3 original locations with exact, GLB bias, sourceRoot, and indexed section support, but remains limited to script URL / line-number style breakpoints; retained paused-session live continuation is in-process only and is exposed through `continuation_preflight`, while durable paused-session snapshots are inspect-only and cannot resume / step / evaluate the original CDP paused execution; page-level mutation audit is a coarse before/after summary while MutationObserver timeline is an explicit-trigger finite DOM record baseline rather than JS heap timeline or object graph diff; source-map name resolution / complex URL semantics / complex indexed section semantics, JS heap fine-grained mutation audit, arbitrary runtime cache introspection, automatic wrapper hook support for arbitrary closure-internal functions, automatic full cross-request timeline materialization without explicit review approval, richer conflict resolver / cross-run physical rollback transaction state machine / cross-run transaction idempotency hardening / external delivery executor, and cross-process live CDP paused execution continuation are intentionally separate follow-up capabilities; native-web recon flow timeline, per-entry correlation hints, conservative correlation groups, group verification readiness, manual stitch candidates, review-gated stitch proposals, reviewer-approved stitched-flow materialization, and explicit flow timeline continuation are available as baselines.

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

Step 38 execution record: ExternalDeliveryProvider registry / entry-point discovery baseline is implemented. It adds `ExternalDeliveryProviderRegistry`, `ExternalDeliveryProviderRegistration`, `ExternalDeliveryProviderCapabilities`, `ExternalDeliveryProviderFactory`, the `reverse_deepagent.external_delivery_providers` entry-point group, and `build_default_external_delivery_provider_registry()`. The default registry registers `review-only` plus `noop` / `manual-handoff` aliases, loads provider registrations from entry points without invoking provider factories, rejects duplicate keys and capability id mismatches, and lets `LocalDeliveryExecutor` resolve `external_delivery_provider_id` through the registry when a provider object is not injected. It still does not ship a real release / webhook / object-storage / GitHub Release provider; those are plugin follow-ups behind the registry contract.

Step 39 execution record: ExternalDeliveryProvider doctor / metadata CLI baseline is implemented with `reverse-agent-doctor --external-delivery-providers`, `ExternalDeliveryProviderRegistry.list_registration_metadata()`, and `external_delivery_provider_matrix`. The doctor output lists provider ids, aliases, the `reverse_deepagent.external_delivery_providers` entry-point group, transport, `review_only`, `supports_external_delivery`, summary counts, and a side-effect policy while skipping CDP port probes, not requiring MCP / Chrome, and not invoking provider factories. It still does not ship or call a real network release / webhook / object-storage / GitHub Release provider; those remain plugin follow-ups behind the registry contract.

Step 40 execution record: external delivery idempotency / duplicate guard baseline is implemented. `DeliveryExecutorConfig` now accepts `external_delivery_idempotency_key` plus `allow_duplicate_external_delivery`; the idempotency key defaults to the transaction id and is written into package / journal metadata. When a previous `delivery-transaction-journal.json` or `external-delivery-result.json` in the same delivery root reports `external_delivery_performed=true`, a later external delivery request is blocked before invoking the provider factory / provider and writes `external-delivery-duplicate-guard.json`, while preserving the previous journal performed state and original external result path. An explicit `allow_duplicate_external_delivery=true` is required for a reviewed retry. This is a duplicate-call guard, not a full cross-run transaction state machine and not a real release / webhook / object-storage / GitHub Release provider.

Step 41 execution record: LocalArchiveExternalDeliveryProvider / filesystem-release baseline is implemented. The default external delivery registry now includes `local-archive` plus `filesystem-release` / `archive` aliases, and `reverse-agent-doctor --external-delivery-providers` reports it as `transport=filesystem`, `supports_external_delivery=true`, and `review_only=false` without invoking provider factories. `DeliveryExecutorConfig` now accepts `external_delivery_provider_config`, and `execute_local_delivery` exposes `external_delivery_provider_config_json` so provider-specific options such as `archive_root` can be passed through. In dry-run, local-archive is side-effect-free and returns a planned result; in apply mode it copies already delivered artifacts into a deterministic local archive release directory and writes `local-archive-manifest.json` plus `local-archive-checksums.json`, with paths recorded in `external-delivery-result.json` metadata. This is the first real external delivery provider boundary, but it is intentionally filesystem-only: it does not upload to network services, create GitHub Releases, bypass review, or bypass the duplicate guard / transaction limitations.
