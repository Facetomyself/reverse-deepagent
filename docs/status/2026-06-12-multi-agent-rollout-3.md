# 2026-06-12 Multi-agent unfinished-work rollout 3

## Purpose

This document tracks the third multi-agent rollout for planned-but-not-fully-implemented work after the second rollout moved S3-compatible delivery, AntiDetect allocator contract, and GitLab Release asset upload into baseline.

The main agent owns coordination, review, merge order, final validation, and ROADMAP / status updates. Worker agents own bounded implementation PRs with disjoint write scopes.

## Base branch

- Base branch: `refactor/consolidate-hooks-native-web`
- Base commit at dispatch time: `261b8a64`
- Second rollout final validation before dispatch: `1725` unit tests passing with `2` skipped.
- Open PRs at dispatch time: none.

## Worker assignments

| Worker | Branch | Planned PR scope | Primary ownership | Non-goals |
| --- | --- | --- | --- | --- |
| Worker G | `codex/internal-artifact-registry-delivery` | Internal artifact registry `ExternalDeliveryProvider` package baseline | `packages/reverse-deepagent-external-delivery-provider-internal-registry/`, `tests/test_external_delivery_provider_plugin_internal_registry.py` | No SDK dependency, no network in tests, no raw endpoint query / headers / response leakage, no core delivery rewrite unless strictly required |
| Worker H | `codex/strategy-detector-reference-provider` | Reference StrategyDetector provider package baseline | `packages/reverse-deepagent-strategy-detector-reference/`, provider-specific tests | No browser launch, no runtime context collection, no replay execution, no MCP, no external file / network reads in metadata listing |
| Worker I | `codex/source-map-terminal-action` | Source Map terminal review action decision / result recorder baseline | `src/reverse_deepagent/browser/source_maps.py`, `tests/test_source_maps.py` | No debugger continuation, no hook / logpoint install, no rebuild generation, no Source Map fetch, no raw source export |

## Main-agent merge gates

Each worker PR must prove:

1. It targets `refactor/consolidate-hooks-native-web`.
2. It uses an isolated worktree and a narrow branch.
3. It has a narrow, reviewable diff and does not revert unrelated worker or main-agent work.
4. Metadata / registry / doctor listing remains side-effect-free.
5. Dry-run or review-only paths do not perform network IO, browser launch, provider allocation, file upload, hook installation, debugger continuation, rebuild generation, Source Map fetch, raw-source export, or secret reads.
6. Apply / publication / terminal decision paths require explicit review approval flags or explicit reviewer fields.
7. Sensitive values are redacted from artifacts, events, metadata, errors, and tests.
8. Inline secret material in URLs or endpoints is blocked or conservatively marked unsafe.
9. Tests cover side-effect policy, approval / reviewer gates, secret redaction, and the new positive path through mocked or pure-Python seams.
10. The worker reports exact validation commands.

## Expected merge order

1. Worker H: StrategyDetector reference provider is an isolated new package and should not affect runtime behavior.
2. Worker G: Internal artifact registry provider is an isolated new delivery package and can land before delivery docs are updated.
3. Worker I: Source Map terminal action touches the large Source Map manager/test surface and should merge after the isolated package PRs.

If a PR has conflicts, the main agent should request a worker update or rebase inside that worker branch rather than manually mixing unrelated worker scopes.

## Completion definition for this rollout

This rollout is complete only when:

- All accepted worker PRs are reviewed and merged into `refactor/consolidate-hooks-native-web`.
- The branch is pushed to `origin/refactor/consolidate-hooks-native-web`.
- `git status --short --branch` is clean except ignored local artifacts.
- `git diff --check` passes.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src/reverse_deepagent tests packages/reverse-deepagent-external-delivery-provider-internal-registry/src packages/reverse-deepagent-strategy-detector-reference/src` passes, adjusted if a scoped PR is intentionally not accepted.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` passes, or any failure is explicitly attributed to an external service gate outside the pure-Python test suite.
- ROADMAP / status docs are updated to reflect which unfinished items moved from active gap to baseline shipped.

## Execution result

Pending worker PRs.

## Final validation status

Pending worker PR review, merge, and full validation.
