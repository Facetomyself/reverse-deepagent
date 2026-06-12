# 2026-06-12 Multi-agent unfinished-work rollout 2

## Purpose

This document tracks the second multi-agent rollout for planned-but-not-fully-implemented work after the first rollout moved Source Map candidate ranking, AntiDetect hosted CDP attach-only support, and GitLab Release record creation into baseline.

The main agent owns coordination, review, merge order, final validation, and ROADMAP / status updates. Worker agents own bounded implementation PRs with disjoint write scopes.

## Base branch

- Base branch: `refactor/consolidate-hooks-native-web`
- Base commit at dispatch time: `90213165`
- First rollout final validation before dispatch: `1709` unit tests passing with `2` skipped.
- Open PRs at dispatch time: none.

## Worker assignments

| Worker | Branch | Planned PR scope | Primary ownership | Non-goals |
| --- | --- | --- | --- | --- |
| Worker D | `codex/s3-compatible-delivery-provider` | S3-compatible `ExternalDeliveryProvider` plugin baseline | `packages/reverse-deepagent-external-delivery-provider-s3-compatible/`, `tests/test_external_delivery_provider_plugin_s3_compatible.py` | No boto3 hard dependency, no network in tests, no secret/header/query leakage, no core delivery rewrite unless strictly required |
| Worker E | `codex/gitlab-release-asset-upload` | GitLab Release binary asset upload baseline | `packages/reverse-deepagent-external-delivery-provider-gitlab-release/`, `tests/test_external_delivery_provider_plugin_gitlab_release.py` | No SDK dependency, no regression of release-record baseline, no token/header/body leakage, no unrelated provider changes |
| Worker F | `codex/antidetect-allocator-contract` | AntiDetect hosted CDP vendor-neutral allocator contract baseline | `packages/reverse-deepagent-browser-provider-antidetect-cdp/`, `tests/test_browser_provider_plugin_antidetect_cdp.py`, optional AntiDetect-specific smoke readiness rule | No implicit browser launch, no env secret reads in metadata, no vendor SDK requirement, no changes to unrelated providers |

## Main-agent merge gates

Each worker PR must prove:

1. It targets `refactor/consolidate-hooks-native-web`.
2. It uses an isolated worktree and a narrow branch.
3. It has a narrow, reviewable diff and does not revert unrelated worker or main-agent work.
4. Metadata / registry / doctor listing remains side-effect-free.
5. Dry-run paths do not perform network IO, browser launch, provider allocation, file upload, or secret reads.
6. Apply / allocation / upload paths require explicit review approval flags.
7. Sensitive values are redacted from artifacts, events, metadata, errors, and tests.
8. Inline secret material in URLs or endpoints is blocked or conservatively marked unsafe.
9. Tests cover side-effect policy, approval gates, secret redaction, and the new positive path through mocked seams.
10. The worker reports exact validation commands.

## Expected merge order

1. Worker D: S3-compatible provider is a new package and should be easiest to merge first.
2. Worker F: AntiDetect allocator contract touches browser-provider plugin readiness metadata and may affect provider smoke matrix tests.
3. Worker E: GitLab asset upload extends an existing provider with more partial-failure states and should merge after the new-provider baseline so delivery docs can be updated once.

If a PR has conflicts, the main agent should request a worker update or rebase inside that worker branch rather than manually mixing unrelated worker scopes.

## Completion definition for this rollout

This rollout is complete only when:

- All accepted worker PRs are reviewed and merged into `refactor/consolidate-hooks-native-web`.
- The branch is pushed to `origin/refactor/consolidate-hooks-native-web`.
- `git status --short --branch` is clean except ignored local artifacts.
- `git diff --check` passes.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src/reverse_deepagent tests packages/reverse-deepagent-browser-provider-antidetect-cdp/src packages/reverse-deepagent-external-delivery-provider-gitlab-release/src packages/reverse-deepagent-external-delivery-provider-s3-compatible/src` passes, adjusted if a scoped PR is intentionally not accepted.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` passes, or any failure is explicitly attributed to an external service gate outside the pure-Python test suite.
- ROADMAP / status docs are updated to reflect which unfinished items moved from active gap to baseline shipped.

## Execution result

Pending worker PRs.

## Final validation status

Pending worker PR review, merge, and full validation.
