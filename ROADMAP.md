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
- CloakBrowser optional provider skeleton, launch / persistent-context / connect baseline, manual smoke path, and explicit workspace smoke evidence capture path.
- Browser provider doctor mode, side-effect-free provider matrix, `reverse-agent-browser-provider-smoke` workspace evidence CLI with metadata-only default / explicit launch smoke mode, and `reverse-agent-demo --browser-provider-smoke-json` attachment of reviewed existing smoke evidence into Web pipeline manifests.
- BrowserProvider production readiness metadata baseline that classifies provider rows as `production-ready`, `review-required`, or `metadata-incomplete` without invoking provider factories, probing CDP, launching browsers, or calling MCP.
- Provider-specific production readiness rule catalog scaffold, currently covering Playwright Chromium, Remote CDP, CloakBrowser, and hosted-CDP reference lifecycle metadata contracts without invoking provider factories or probing endpoints.
- Extensible BrowserProvider capability compatibility rule catalog for CDP/debugger/network/lifecycle plus proxy, humanize, mobile emulation, and extension capability checks.
- Functional external BrowserProvider fixture plugin package that proves entry-point discovery, metadata-only listing, delayed factory creation, and launch/connect smoke outside core runtime.
- Hosted CDP BrowserProvider template package that gives vendor anti-detect browsers, hosted browser services, and enterprise CDP brokers a provider-neutral external package seam with metadata-only registration and explicit Remote CDP contract smoke.
- Hosted CDP reference BrowserProvider package that models allocation / attach / release lifecycle, idempotent stop, redacted metadata, and launch smoke through the BrowserProvider contract without bundling a vendor SDK.
- Managed Chrome debug launcher scripts and docs.
- MCP legacy downgrade, alias warnings, and optional legacy MCP package split.

### Native Web collectors and hooks

- DOM, console, script inventory, navigation events, network metadata, request initiator, response body metadata, source cache, and WebSocket frame cache with fallback paths.
- Fetch / XHR / cookie / WebSocket / anti-debug hook baselines.
- Target-function wrapper and webpack-like module export hook baselines.
- Module discovery, runtime module cache / registry introspection, custom object runtime, module federation function-path candidate baseline, read-only async chunk graph / loader metadata baseline, review-only custom-loader traversal plan baseline, and review-gated webpack async chunk load plan / explicit execution evidence baseline.
- Closure-scope function discovery baseline without automatic closure wrapper replacement.
- Source-level logpoints and Source Map exact / bias / sourceRoot / indexed-section remap baseline, with source-map `names` metadata, URL-like source equivalence, nested indexed-section stack metadata, and review-gated credentialless external Source Map / indexed-section URL fetch metadata baseline.
- Page mutation audit, descriptor-safe scoped object-root mutation audit, and MutationObserver timeline baselines.
- Same-process paused-session continuation and durable inspect-only paused-session snapshots.

### DeepAgents workspace and subagents

- DeepAgents workspace contract indexed-only baseline.
- Manifest-only workspace alias for future foldered virtual paths while keeping flat `workspace/*.json` paths canonical.
- Workspace artifact reader, specialized read-only review-helper artifact-ref resolver, rebuild generation artifact-ref inputs, delivery artifact-list resolver, delivery source compatibility audit, workspace migration readiness report, limited dual-write pilot plan / scoped writer / result artifact / review workflow, pure-Python reviewed scoped dual-write pilot smoke CLI, resolver compatibility metrics, and workspace consumer adoption audit baselines for artifact key, legacy path, future path, `virtual://workspace/...` URI, artifact-root-relative consumption, explicit source_path classification, scoped dual-write output verification, and reviewed local delivery planning / apply inputs by coordinator, review / rebuild / timeline / hook / debugger / delivery subagents.
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

- Real third-party BrowserProvider plugins beyond the functional fixture, hosted-CDP template, and hosted-CDP reference packages, such as concrete vendor anti-detect browsers or hosted browser services; new providers should preserve the reference allocation / attach / release lifecycle, fill the production readiness metadata contract, and provide `workspace/browser-provider-smoke.json` evidence before runtime smoke is accepted.
- Additional provider-specific compatibility / readiness rules when real third-party provider plugins introduce new capability flags or lifecycle policies beyond the built-in provider baseline.
- Cross-process live CDP paused execution continuation.
- Execution-style arbitrary custom loader traversal, deep async chunk traversal, and broader async chunk loading beyond the current review-only custom-loader traversal plan and review-gated webpack ensure baselines.
- Execution-style module federation `get/init` analysis beyond the current read-only runtime-path baseline.
- Opt-in wrapper replacement for closure-internal functions beyond paused-callframe evidence.
- Bundler-specific symbol scoping and full source-map consumer semantics beyond the current local remap plus review-gated credentialless URL fetch metadata baseline.
- Deeper JS heap / object graph diff beyond the current descriptor-safe scoped object-root mutation audit baseline.

### Strategy and rebuild quality

- Broader evidence scoring consumer adoption in review / delivery gates if downstream automation needs it.
- Strategy detector pluginization if the built-in strategy corpus grows too large.

### Workspace and artifact evolution

- Use `reverse-agent-workspace-dual-write-smoke` / `review_workspace_dual_write_pilot_workflow` evidence from reviewed scoped dual-write runs before any broader dual-write rollout or foldered-canonical migration pilot; current smoke and workflow intentionally keep high-risk delivery / transaction artifacts out of default pilots and keep foldered-canonical migration blocked while partial consumers or `source_path` usage remain.
- Opt-in dual-write expansion informed by resolver compatibility metrics.
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
