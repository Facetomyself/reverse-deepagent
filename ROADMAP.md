# Roadmap

This roadmap is status-based. The detailed execution log lives in `.codex/plans/browser-provider-mcp-deprecation-plan.md` and `docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md`.

## Current direction

The project keeps the Web / JS reverse-engineering path as the mainline:

- `native-web + BrowserProvider + native collectors / hooks` is the canonical Web runtime path.
- `legacy-mcp` remains a compatibility backend and is supplied through the optional legacy MCP package.
- Browser implementations stay pluggable through `BrowserProvider` registrations instead of becoming coordinator dependencies.
- Delivery / review / rollback / lock workflows remain review-gated and side-effect explicit.
- Android, iOS, and mini-program full runtime chains remain deferred; only minimal adapter metadata, explicit tool probes, and platform-neutral artifact categories are maintained for now.

## Done / baseline shipped

These items have baseline implementations and tests. Some are intentionally conservative and remain review-only, dry-run-only, or explicit-approval-only.

### Web runtime and browser provider baseline

- BrowserProvider contract and registry.
- Playwright Chromium provider.
- Remote CDP provider.
- CloakBrowser optional provider skeleton, launch / persistent-context / connect baseline, and manual smoke path.
- Browser provider doctor mode and side-effect-free provider matrix.
- Extensible BrowserProvider capability compatibility rule catalog for CDP/debugger/network/lifecycle plus proxy, humanize, mobile emulation, and extension capability checks.
- Functional external BrowserProvider fixture plugin package that proves entry-point discovery, metadata-only listing, delayed factory creation, and launch/connect smoke outside core runtime.
- Managed Chrome debug launcher scripts and docs.
- MCP legacy downgrade, alias warnings, and optional legacy MCP package split.

### Native Web collectors and hooks

- DOM, console, script inventory, navigation events, network metadata, request initiator, response body metadata, source cache, and WebSocket frame cache with fallback paths.
- Fetch / XHR / cookie / WebSocket / anti-debug hook baselines.
- Target-function wrapper and webpack-like module export hook baselines.
- Module discovery, runtime module cache / registry introspection, custom object runtime, and module federation function-path candidate baseline.
- Closure-scope function discovery baseline without automatic closure wrapper replacement.
- Source-level logpoints and Source Map exact / bias / sourceRoot / indexed-section remap baseline.
- Page mutation audit and MutationObserver timeline baselines.
- Same-process paused-session continuation and durable inspect-only paused-session snapshots.

### DeepAgents workspace and subagents

- DeepAgents workspace contract indexed-only baseline.
- Manifest-only workspace alias for future foldered virtual paths while keeping flat `workspace/*.json` paths canonical.
- Read-only workspace artifact reader resolver baseline for artifact key, legacy path, future path, `virtual://workspace/...` URI, and artifact-root-relative consumption by coordinator and review / rebuild / timeline / hook / debugger subagents.
- Router, web recon, browser runtime, debugger, hook, timeline, review, rebuild, and delivery subagent baselines.
- Review approval ledger baseline.

### Flow timeline and review-gated materialization

- Flow timeline baseline with correlation hints, conservative correlation groups, manual stitch candidates, and review-gated stitch proposals.
- Auto-stitch dry-run scoring, policy decision gate, materialization plan, review-approved materializer skeleton, conflict resolver baseline, materialization audit / rollback writer, transaction log, rollback dry-run, review gate recompute, and final delivery package / transaction record baselines.
- Automatic stitching and automatic delivery remain disabled by design.

### Delivery, recovery, lock, and external delivery baselines

- Local delivery executor contract and manifest revision baseline.
- Backend artifact manifest mutation policy, in-place mutation preflight, explicit-review-only in-place mutation, recovery preflight, recovery apply, and cross-run transaction commit baselines.
- Delivery transaction inspector / doctor, transition executor, recovery executor, idempotency guard, rollback state writer, rollback preflight, and explicit-review-only rollback apply baselines.
- Delivery resume planner, resume runner, resume workflow scheduler, workflow journal, skipped-step journal context replay, workflow-local fencing propagation, journal-state fencing replay, lock lifecycle planning, lease renewal planning, workflow readiness plan, step dependency context matrix, and runtime-gate evidence projection.
- Delivery transaction lock provider contract with local-file, SQLite, and Redis baselines.
- ExternalDeliveryProvider contract and registry with local archive, webhook, presigned object, GitHub Release upload / reuse / duplicate preflight / overwrite-delete, explicit retry, idempotency ledger, and optional provider template.

### Platform expansion boundary

- Android adapter interface draft and minimal `android-adb` backend metadata / explicit ADB probe / artifact export baseline.
- iOS adapter interface draft and minimal `ios-simulator` backend metadata / explicit `xcrun simctl` probe / artifact export baseline.
- Mini-program adapter interface draft and minimal `mini-program-devtools` metadata / configurable vendor-devtools probe / artifact export baseline.
- Platform-neutral artifact categories and `target_platforms` semantics.

### Strategy and rebuild quality baseline

- Generalized runtime context stability diff for legacy runtime payloads and provider-neutral strategy / rebuild consumers.
- Field-level runtime context classifications for stable, volatile, session-bound, missing, type-drift, and object-drift values.
- Secret-like runtime context previews redacted to type, length, and digest metadata while preserving legacy `stable_keys` / `volatile_keys` / `changes` compatibility fields.
- Generated rebuild review hints derived from runtime-context diff classifications for volatile, session-bound, missing, type-drift, and object-drift fields.
- Plan-only WASM / VM / obfuscation triage hook planner with protected-flow hook/debugger candidates and workspace artifact routes.
- Provider-neutral strategy evidence scoring baseline that combines detector confidence, validation status, replay URL presence, runtime-context stability, protected-flow triage, and rebuild readiness into review-only `evidence_score` payloads.

## Active non-mobile follow-ups

These are the next realistic non-mobile work items. They should be implemented without leaking provider-specific details into the coordinator.

### Documentation and governance

- Keep `ROADMAP.md`, `.codex/plans/`, README, AGENTS, and runtime docs aligned after each architecture-level change.
- Split long future-work paragraphs into completed baseline, active remaining work, and explicitly deferred automation.

### Browser / CDP / hook depth

- Production third-party BrowserProvider plugins beyond the functional fixture provider, such as vendor anti-detect browsers or hosted browser services.
- Provider-specific compatibility rule additions when real third-party provider plugins introduce new capability flags.
- Cross-process live CDP paused execution continuation.
- Arbitrary custom loader traversal and async chunk graph analysis.
- Execution-style module federation `get/init` analysis beyond the current read-only runtime-path baseline.
- Opt-in wrapper replacement for closure-internal functions beyond paused-callframe evidence.
- Richer Source Map name, URL, and complex indexed-section semantics.
- Scoped JS heap / object-root mutation audit and object graph diff.

### Strategy and rebuild quality

- Broader evidence scoring consumer adoption in review / delivery gates if downstream automation needs it.
- Strategy detector pluginization if the built-in strategy corpus grows too large.

### Workspace and artifact evolution

- Broader consumer adoption of workspace aliases and virtual workspace folders beyond the coordinator and review / rebuild / timeline / hook / debugger reader baseline.
- Resolver adoption in delivery and specialized review helpers before any physical folder migration.
- Opt-in dual-write expansion with compatibility metrics.
- A narrow foldered-canonical migration pilot only after consumers support the resolver.

### Delivery and external integration hardening

- Broader durable resume scheduler semantics beyond read-only readiness / dependency / evidence projection.
- Broader physical rollback state machine beyond local manifest rollback apply.
- Additional external distributed lock providers beyond local-file / SQLite / Redis where deployment needs justify them.
- Real third-party ExternalDeliveryProvider plugins beyond the template, such as S3-compatible storage or GitLab Release.
- Advanced adaptive provider retry policy, retry budgets, and provider-specific rate-limit behavior.
- More complete external delivery partial-failure recovery.

## Explicitly deferred

These items are intentionally not part of the current Web-first execution track:

- Android full runtime chain, Frida workflows, APK / dex / JNI deep analysis, and device CI.
- iOS full runtime chain, Frida / LLDB workflows, IPA / Mach-O deep analysis, signing-dependent workflows, and device CI.
- Mini-program full runtime chain, private package extraction, account-bound developer-tool sessions, and bridge-bound signing workflows.
- Automatic lease-renewal daemon or polling loop.
- Automatic lock lifecycle manager.
- Automatic stale lock takeover.
- Redlock quorum consensus.
- Unreviewed automatic full cross-request materialization.
- Automatic rollback-vs-commit decision making.
- Automatic external delivery publication without explicit review / apply intent.

## Validation posture

- Public CI should stay focused on mock, pure-Python, and side-effect-free paths.
- Real browser, CloakBrowser, remote CDP, legacy MCP, Redis, object storage, or GitHub Release smoke tests must remain explicit local or self-hosted checks.
- Provider metadata listing, doctor matrix output, registry discovery, and workspace contract export must stay side-effect-free.
