# 2026-06-12 Multi-agent unfinished-work rollout

## Purpose

This document tracks the first multi-agent rollout for planned-but-not-fully-implemented work after the 2026-06-10 refactor audit. The main agent owns coordination, review, merge order, and final plan/status updates. Worker agents own bounded implementation PRs with disjoint write scopes.

## Base branch

- Base branch: `refactor/consolidate-hooks-native-web`
- Base commit at dispatch time: `9ed8f8419edc7a616e7dd707dbba409b5db351c3`
- Validation baseline before dispatch: `1695` unit tests passing with `2` skipped.

## Worker assignments

| Worker | Branch | Planned PR scope | Primary ownership | Non-goals |
| --- | --- | --- | --- | --- |
| Worker A | `codex/source-map-ranking-baseline` | Source Map follow-through candidate ranking metadata | `src/reverse_deepagent/browser/source_maps.py`, `tests/test_source_maps.py` | No browser launch, no CDP command, no MCP, no raw source export, no debugger / hook install without explicit review |
| Worker B | `codex/gitlab-release-delivery-provider` | GitLab Release external delivery provider package baseline | `packages/reverse-deepagent-external-delivery-provider-gitlab-release/`, package-specific tests | No real network in tests, no token/header leakage, no core delivery rewrite unless strictly required |
| Worker C | `codex/antidetect-cdp-browser-provider` | Anti-detect hosted CDP BrowserProvider package baseline | `packages/reverse-deepagent-browser-provider-antidetect-cdp/`, package-specific tests | No implicit browser launch, no vendor SDK requirement, no secret reads during metadata listing |

## Main-agent merge gates

Each worker PR must prove:

1. It targets `refactor/consolidate-hooks-native-web`.
2. It has a narrow, reviewable diff and does not revert unrelated work.
3. It keeps metadata / registry / doctor listing side-effect-free.
4. It keeps sensitive values redacted in artifacts, logs, metadata, and tests.
5. It adds tests for the new behavior and reports the exact commands run.
6. It passes at least its targeted tests before merge.
7. After merge, the main agent reruns integration checks appropriate to the touched surface and a final full unittest sweep before marking the rollout complete.

## Expected merge order

1. Worker A: Source Map ranking is mostly core pure-Python and should land before related roadmap text is finalized.
2. Worker C: BrowserProvider plugin baseline touches provider package / registry surface and may affect doctor metadata.
3. Worker B: ExternalDeliveryProvider plugin baseline may add package metadata and delivery test surface.

If a PR has conflicts, the main agent should rebase or request a worker update rather than manually mixing unrelated worker scopes.

## Completion definition for this rollout

This rollout is complete only when:

- All accepted worker PRs are merged into `refactor/consolidate-hooks-native-web`.
- The branch is pushed to `origin/refactor/consolidate-hooks-native-web`.
- `git status --short --branch` is clean except ignored local artifacts.
- `git diff --check` passes.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src/reverse_deepagent tests` passes.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` passes, or any failure is explicitly attributed to an external service gate outside the pure-Python test suite.
- ROADMAP / status docs are updated to reflect which unfinished items moved from active gap to baseline shipped.

## Execution result

| Worker | PR | Merge commit | Result | Main-agent verification |
| --- | --- | --- | --- | --- |
| Worker A | [#21](https://github.com/Facetomyself/reverse-deepagent/pull/21) | `3a07f7c8` | Merged | `tests.test_source_maps`, `compileall`, `git diff --check` |
| Worker C | [#23](https://github.com/Facetomyself/reverse-deepagent/pull/23) | `5e134704` | Merged | `tests.test_browser_provider_plugin_antidetect_cdp`, `tests.test_browser_smoke_matrix`, `tests.test_browser_provider_registry`, `tests.test_doctor`, `compileall`, `git diff --check` |
| Worker B | [#22](https://github.com/Facetomyself/reverse-deepagent/pull/22) | `c1367b7c` | Merged after security review fix | `tests.test_external_delivery_provider_plugin_gitlab_release`, `tests.test_external_delivery_registry`, `tests.test_doctor`, `compileall`, `git diff --check`; main review required inline-secret `api_base_url` blocker before merge |

## Scope moved to baseline

- Source Map debugger / hook candidate review descriptors now include deterministic, review-only ranking metadata. Automatic debugger / hook execution remains out of scope without explicit review.
- AntiDetect hosted CDP now has a vendor-neutral external BrowserProvider package baseline with attach-only reviewed endpoint support and provider-specific readiness rules. Vendor allocation / SDK integration remains out of scope.
- GitLab Release now has an external delivery provider package baseline for reviewed release-record creation with dry-run no-network behavior, explicit apply approval, metadata redaction, and inline-secret API URL blocking. Binary asset upload and partial-failure recovery remain follow-ups.

## Final validation status

Passed on 2026-06-12 after merging PR #21, PR #23, and PR #22, then updating ROADMAP / status documentation:

- `git diff --check`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests packages/reverse-deepagent-browser-provider-antidetect-cdp/src packages/reverse-deepagent-external-delivery-provider-gitlab-release/src`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v` (`1709` tests, `2` skipped)
