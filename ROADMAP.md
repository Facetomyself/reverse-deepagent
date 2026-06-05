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

- Runtime documentation governance baseline that splits the native-web capability description into implemented baseline, explicit reviewed execution surfaces, active Web-first gaps, and explicitly deferred automation / non-Web chains.

### Web runtime and browser provider baseline

- BrowserProvider contract and registry.
- Playwright Chromium provider.
- Remote CDP provider.
- CloakBrowser optional provider skeleton, launch / persistent-context / connect baseline, manual smoke path, and explicit workspace smoke evidence capture path.
- Browser provider doctor mode, side-effect-free provider matrix, `reverse-agent-browser-provider-smoke` workspace evidence CLI with metadata-only default / explicit launch smoke mode, and `reverse-agent-demo --browser-provider-smoke-json` attachment of reviewed existing smoke evidence into Web pipeline manifests.
- BrowserProvider production readiness metadata baseline that classifies provider rows as `production-ready`, `review-required`, or `metadata-incomplete` without invoking provider factories, probing CDP, launching browsers, or calling MCP.
- Provider-specific production readiness rule catalog scaffold, currently covering Playwright Chromium, Remote CDP, CloakBrowser, hosted-CDP reference, and Browserless CDP lifecycle metadata contracts without invoking provider factories or probing endpoints.
- Extensible BrowserProvider capability compatibility rule catalog for CDP/debugger/network/lifecycle plus proxy, humanize, mobile emulation, and extension capability checks.
- Functional external BrowserProvider fixture plugin package that proves entry-point discovery, metadata-only listing, delayed factory creation, and launch/connect smoke outside core runtime.
- Hosted CDP BrowserProvider template package that gives vendor anti-detect browsers, hosted browser services, and enterprise CDP brokers a provider-neutral external package seam with metadata-only registration and explicit Remote CDP contract smoke.
- Hosted CDP reference BrowserProvider package that models allocation / attach / release lifecycle, idempotent stop, redacted metadata, and launch smoke through the BrowserProvider contract without bundling a vendor SDK.
- Browserless CDP BrowserProvider package baseline with side-effect-free entry-point registration, HTTP DevTools endpoint delegation, direct browser WebSocket CDP Target/Page/Runtime support, secret-safe endpoint metadata, explicit smoke path, and provider-specific readiness rule coverage.
- Managed Chrome debug launcher scripts and docs.
- MCP legacy downgrade, alias warnings, and optional legacy MCP package split.

### Native Web collectors and hooks

- DOM, console, script inventory, navigation events, network metadata, request initiator, response body metadata, source cache, and WebSocket frame cache with fallback paths.
- Fetch / XHR / cookie / WebSocket / anti-debug hook baselines.
- Target-function wrapper and webpack-like module export hook baselines.
- Module discovery, runtime module cache / registry introspection, custom object runtime, module federation function-path candidate baseline, review-only module federation `get/init` plan baseline, review-gated module federation `init/get` probe baseline, review-gated remote factory invocation / export-summary baseline, review-only remote export hook selection plan baseline, review-approved remote export hook install baseline, review-only federation traversal graph / workflow plan, review-gated traversal workflow execution, review-only federation recursive traversal follow-up plan, review-gated federation recursive traversal follow-up checkpoint, and review-gated federation recursive traversal next-step execution baselines, read-only async chunk graph / loader metadata baseline, review-only custom-loader traversal plan baseline, bounded custom-loader traversal continuation planning baseline, review-only custom-loader traversal graph / queue baseline, review-only multi-step custom-loader traversal workflow plan baseline, review-gated custom-loader traversal workflow execution baseline, review-only bounded custom-loader traversal loop plan baseline, review-gated bounded custom-loader traversal loop execution baseline, review-only custom-loader recursive traversal follow-up plan baseline, review-gated custom-loader recursive traversal follow-up checkpoint baseline, review-gated custom-loader recursive traversal next-loop execution baseline, review-only custom-loader continuation workflow planning baseline, review-gated custom-loader continuation journal baseline, review-approved one-step custom-loader continuation execution baseline, side-effect-free custom-loader execution preflight baseline, review-approved single-step custom-loader execution result baseline, review-only custom-loader module diff / hook candidate refresh baseline, review-approved custom-loader module hook follow-through baseline, review-gated webpack async chunk load plan / explicit execution evidence baseline, review-only async chunk traversal graph / queue baseline, review-only async chunk traversal workflow plan baseline, review-gated async chunk traversal workflow execution baseline, review-only bounded async chunk traversal loop plan baseline, review-gated bounded async chunk traversal loop execution baseline, review-only async chunk recursive traversal follow-up plan baseline, review-gated async chunk recursive traversal follow-up checkpoint baseline, review-gated async chunk recursive traversal next-loop execution baseline, review-only async chunk module diff / hook candidate refresh baseline, and review-approved async chunk module hook follow-through baseline.
- Closure-scope function discovery baseline, review-only closure wrapper replacement planning baseline, opt-in same-process reviewed closure wrapper replacement execution MVP with restore-plan artifact, reviewed same-process closure wrapper restore execution baseline, and read-only closure wrapper event harvesting artifact baseline; arbitrary automatic closure wrapper replacement remains unsupported.
- Source-level logpoints and Source Map exact / bias / sourceRoot / indexed-section remap baseline, with source-map `names` metadata, URL-like source equivalence, nested indexed-section stack metadata, and review-gated credentialless external Source Map / indexed-section URL fetch metadata baseline.
- Page mutation audit, descriptor-safe scoped object-root mutation audit, and MutationObserver timeline baselines.
- Same-process paused-session continuation, durable inspect-only paused-session snapshots, and read-only paused-session live-continuation preflight evidence for same-process / durable / provided-artifact debugger state.

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
- Keep long runtime and delivery status sections split into implemented baseline, active remaining work, and explicitly deferred automation as new architecture-level changes land.

### Browser / CDP / hook depth

- Additional real third-party BrowserProvider plugins beyond the Browserless CDP baseline, functional fixture, hosted-CDP template, and hosted-CDP reference packages, such as concrete vendor anti-detect browsers or other hosted browser services; new providers should preserve explicit metadata-only registration, fill the production readiness metadata contract, and provide `workspace/browser-provider-smoke.json` evidence before runtime smoke is accepted.
- Additional provider-specific compatibility / readiness rules when real third-party provider plugins introduce new capability flags or lifecycle policies beyond the built-in provider baseline.
- Cross-process live CDP paused execution continuation beyond the read-only live-continuation preflight baseline.
- Deeper execution-style custom-loader traversal beyond one reviewed recursive next-loop checkpoint and the current bounded continuation planning, review-only traversal graph / queue, review-only multi-step traversal workflow plan, review-gated traversal workflow execution, review-only bounded traversal loop planning, review-gated bounded traversal loop execution, review-only recursive traversal follow-up planning, review-gated recursive traversal follow-up checkpointing, review-gated recursive next-loop execution, review-only continuation workflow planning, review-gated continuation journal, review-approved one-step continuation execution, review-approved single-step custom-loader execution, module-diff refresh, and module hook follow-through baselines remains capability-gated for deeper recursive traversal. Deep async chunk traversal beyond the current review-only traversal graph / queue, review-only traversal workflow plan, review-gated one-step traversal workflow execution, review-only bounded traversal loop planning, review-gated bounded loop execution, review-only recursive traversal follow-up planning, review-gated recursive traversal follow-up checkpointing, review-gated recursive next-loop execution, review-gated webpack ensure, review-only async chunk module diff / hook candidate refresh, and review-approved async chunk module hook follow-through baselines remains capability-gated for deeper multi-iteration traversal.
- Deeper recursive federation traversal and remote-module analysis beyond the current review-only traversal graph / workflow plan, review-gated one-step traversal workflow execution, review-only recursive follow-up planning, review-gated recursive follow-up checkpointing, review-gated recursive next-step execution, review-only recursive continuation journal / multi-step checkpoint planning, review-gated recursive continuation checkpoint execution, reviewed factory invocation / export-summary, review-only export-hook-plan, and review-approved remote export hook install baselines.
- Closure wrapper replacement hardening beyond the current same-process `log-only-call-through` reviewed install / restore execution baselines, including richer assignment safety proofs and cross-process live CDP continuation integration.
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
