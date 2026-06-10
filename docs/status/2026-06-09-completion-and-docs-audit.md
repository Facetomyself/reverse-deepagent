# 2026-06-09 completion and documentation audit

This document is a point-in-time audit of the current `reverse-deepagent` repository state. It does not replace `ROADMAP.md` or the long execution plans; it classifies the implemented baseline, documentation coverage, and known non-closed gaps so future reviews do not confuse review-only descriptors with completed runtime automation.

## Scope

Audited files include:

- `README.md`
- `ROADMAP.md`
- `AGENTS.md`
- `docs/runtime/browser-provider-architecture.md`
- `docs/runtime/cloakbrowser-provider.md`
- `docs/ci/browser-provider-smoke-policy.md`
- `.codex/plans/browser-provider-mcp-deprecation-plan.md`
- `docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md`
- changed source and test files under `src/` and `tests/`

The audit intentionally excludes Android, iOS, and mini-program full runtime chains because those remain explicitly deferred.

## Completion summary

| Area | Current state | Documentation state | Notes |
| --- | --- | --- | --- |
| Native Web runtime | Implemented as the canonical Web path through `native-web`, BrowserProvider, collectors, hooks, debugger surfaces, Source Map descriptors, and heap descriptors. | Covered by `README.md`, `ROADMAP.md`, and `docs/runtime/browser-provider-architecture.md`. | Many surfaces are intentionally review-only, read-only, plan-only, or explicit-approval-only. |
| BrowserProvider abstraction | Implemented for Playwright Chromium, Remote CDP, CloakBrowser baseline, hosted-CDP template/reference packages, Browserless CDP, and Browserbase CDP baseline. | Covered by `README.md`, `ROADMAP.md`, `docs/runtime/browser-provider-architecture.md`, and `docs/runtime/cloakbrowser-provider.md`. | Browser implementations remain pluggable through provider registration; coordinator must not depend on concrete browser implementations. |
| BrowserProvider smoke / CI policy | Implemented side-effect-free metadata paths, explicit launch smoke, review mode, policy gate, and fixture-based public CI checks. | Covered by `README.md`, `docs/runtime/browser-provider-architecture.md`, and `docs/ci/browser-provider-smoke-policy.md`. | This audit fixed the missing public schema mention for `reverse-deepagent.browser-provider-smoke-acceptance.v1`. |
| Legacy MCP split | Implemented as compatibility / optional package direction with aliases and deprecation boundaries. | Covered by runtime docs, legacy MCP setup docs, and plans. | MCP must not become the new runtime abstraction boundary. |
| DeepAgents workspace contract | Implemented indexed-only contract, virtual folders, manifest-only future aliases, and foldered-canonical migration review chain. | Covered by `README.md`, `ROADMAP.md`, `docs/runtime/browser-provider-architecture.md`, `AGENTS.md`, and tests. | Existing flat workspace paths remain canonical unless an explicit reviewed migration executor changes them. |
| Source Map workflow | Implemented lookup, source content metadata, readiness, materialization, selected executor review chain, terminal review, and explicit selected executor MVPs. | Covered by `ROADMAP.md`, `docs/runtime/browser-provider-architecture.md`, and plan logs. | Automatic follow-through, full binding semantics, and raw source export remain unsupported. |
| Heap snapshot workflow | Implemented readiness, metadata collection, diff review chain, bounded summary diff MVP, constructor-growth analysis MVP, retained-size estimate MVP, path-to-root estimate MVP, and proof-plan descriptors. | Covered by `ROADMAP.md`, `docs/runtime/browser-provider-architecture.md`, and plan logs. | Raw heap proof executors, larger-budget second pass, raw heap export, and automatic follow-up execution remain unsupported. |
| Delivery / external provider workflows | Implemented review-gated local / external delivery, transaction, rollback, lock, fencing, and broader rollout review chains. | Covered by `ROADMAP.md`, runtime docs, and plan logs. | Automation daemons and unreviewed external publication remain unsupported. |
| Android / iOS / mini-program | Adapter interface docs and platform-neutral metadata exist; full runtime chains are not implemented. | Covered by adapter interface docs and `ROADMAP.md` deferred section. | This is intentionally out of current Web-first execution scope. |

## Documentation gap fixed in this audit

The BrowserProvider smoke acceptance path had implementation and tests for the outer acceptance schema, but the main docs only named the nested acceptance report schema. The following docs now explicitly name both public layers:

- `README.md`
- `docs/runtime/browser-provider-architecture.md`
- `docs/ci/browser-provider-smoke-policy.md`

Public smoke review schema layers are:

- `attachment_acceptance`: `reverse-deepagent.browser-provider-smoke-acceptance.v1`
- `attachment_acceptance.acceptance_report`: `reverse-deepagent.browser-provider-smoke-acceptance-report.v1`
- `policy_decision`: `reverse-deepagent.browser-provider-smoke-policy-decision.v1`
- policy wrapper output: `reverse-deepagent.browser-provider-smoke-policy-gate.v1`

The audit also confirmed these public artifact paths are documented together with their exact schemas:

- `workspace/workspace-dual-write-plan.json` / `reverse-deepagent.workspace-dual-write-plan.v1`
- `workspace/source-map-fetch-plan.json` / `reverse-deepagent.source-map-fetch-plan.v1`

## Items intentionally not expanded into top-level docs

A source/documentation string scan still finds schema constants that are not spelled out one-by-one in README or runtime overview docs. They fall into three categories and are not treated as missing public documentation unless they become standalone user-facing artifacts or CLI outputs:

1. Internal nested review contracts, such as Source Map dispatcher bounded-input, transaction-preflight gate, journal-writer gate, selected-executor approval package, or result-checkpoint review package schemas.
2. Future executor contracts embedded in plan-only descriptors, such as heap snapshot diff / retained-size executor contract and bounded-input schemas.
3. Workspace contract fixture paths for future folder aliases, such as `workspace/browser/...`, `workspace/debugger/...`, `workspace/runtime/...`, and `workspace/review/...`, which are validated by tests but do not move canonical flat artifacts yet.

The rule for future maintenance is: document public CLI output schemas, top-level workspace artifacts, and workflow entrypoints in user-facing docs; keep deeply nested contract schemas in plan logs, tests, or focused design references unless they become direct integration surfaces.

## Still not fully closed

The following are planned or partially implemented but not complete runtime automation:

> **2026-06-10 clarification**: Heap retained-size estimate MVP, path-to-root estimate MVP, and constructor-growth drilldown analysis MVP are all implemented (see `docs/status/2026-06-10-refactor-audit.md`). The items below refer to **proof executors** and **automation paths** — not to the MVP estimate executors, which are shipped and covered by tests.

- Raw heap file ingestion / export policy and parser sandbox execution.
- Heap retained-size **proof** executor (beyond the implemented estimate MVP; proof requires dominator-tree traversal and `retained_size_proven=True`).
- Heap path-to-root **proof** executor (beyond the implemented estimate MVP; proof requires root-set / incoming-edge walk and reachability verification).
- Raw-heap constructor drilldown **proof** executor (beyond the implemented descriptor-backed MVP; proof requires raw-heap constructor reachability traversal).
- Larger-budget heap diff second-pass execution.
- Automatic heap follow-up execution.
- Automatic Source Map follow-through execution.
- Complete Source Map binding / lexical scope semantics.
- Automatic source-logpoint / debugger / hook application without explicit review.
- Automatic rebuild generation directly from raw Source Map source content.
- Broader third-party BrowserProvider production plugins beyond current baselines and templates.
- Automation daemons for locks, leases, resume scheduling, rollback-vs-commit decisions, or external publication.
- Android, iOS, and mini-program full runtime chains.

## Review checklist for future changes

When adding a new public runtime feature, keep these in sync:

1. Source implementation under `src/reverse_deepagent/`.
2. Focused tests under `tests/`.
3. `workspace_contract.py` when a top-level artifact or virtual alias changes.
4. `README.md` for user-facing commands or output artifacts.
5. `docs/runtime/browser-provider-architecture.md` for runtime architecture and side-effect boundaries.
6. `ROADMAP.md` for completion / gap classification.
7. Plan logs for step-level provenance.
8. `AGENTS.md` only when adding or changing hard execution boundaries.

Do not document a review-only descriptor as an implemented runtime executor. Do not describe metadata-only evidence as real launch smoke. Do not describe future folder aliases as canonical path migration until an explicit reviewed migration executor has completed.
