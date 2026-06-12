# 2026-06-12 Multi-agent unfinished-work rollout 4

## Purpose

This document tracks the fourth multi-agent rollout after rollout 3 moved the reference StrategyDetector provider, internal artifact registry delivery provider, and Source Map terminal review action recorder into baseline.

Rollout 4 focuses on the B3c refactor item from `docs/status/2026-06-10-refactor-audit.md`: continue reducing `NativeWebRuntimeAdapter.apply_minimal_protection`, which still contains a large set of page-using branches after B3a / B3b / Goal-08.

The main agent owns coordination, review, merge order, final validation, and ROADMAP / status updates. Worker agents own bounded implementation PRs with disjoint branch groups inside `src/reverse_deepagent/adapters/native_web.py`.

## Base branch

- Base branch: `refactor/consolidate-hooks-native-web`
- Base commit at dispatch time: `e8536090`
- Rollout 3 final validation before dispatch: `1747` unit tests passing with `2` skipped.
- Open PRs at dispatch time: none.

## Worker assignments

| Worker | Branch | Planned PR scope | Primary ownership | Non-goals |
| --- | --- | --- | --- | --- |
| Worker J | `codex/b3c-paused-session-dispatch` | Extract paused-session branch group from `apply_minimal_protection` into a helper dispatch method | `src/reverse_deepagent/adapters/native_web.py`; optional focused tests only if behavior changes unexpectedly | No behavior changes, no manager rewrites, no Source Map / delivery / workspace changes, no broad formatting |
| Worker K | `codex/b3c-closure-runtime-dispatch` | Extract closure-wrapper / source-logpoint / function-hook branch group from `apply_minimal_protection` into a helper dispatch method | `src/reverse_deepagent/adapters/native_web.py`; optional focused tests only if behavior changes unexpectedly | No behavior changes, no manager rewrites, no paused-session / module federation / custom-loader / async chunk changes, no broad formatting |

## Dispatch boundaries

Worker J should extract only the branch sequence currently covering paused-session execution / plan / probe / breakpoint session actions, starting at `_is_paused_session_automatic_loop_multi_iteration_execution_request(...)` and ending at `_is_paused_session_request(...)`. The new helper should accept `page` explicitly and return `ProtectionResult | None`.

Worker K should extract only the branch sequence currently covering closure wrapper continuation / replacement / restore / event harvest / discovery plus source-logpoint and function-hook install, starting at `_is_closure_wrapper_continuation_next_iteration_execution_request(...)` and ending at `_is_function_hook_request(...)`. The new helper should accept `page` explicitly and return `ProtectionResult | None`.

Both workers must preserve branch order inside their assigned segment and must not move the final fallback hook behavior.

## Main-agent merge gates

Each worker PR must prove:

1. It targets `refactor/consolidate-hooks-native-web`.
2. It uses an isolated worktree and a narrow branch.
3. It only touches the assigned branch group and any minimal tests needed for confidence.
4. It preserves the exact existing manager calls, spec construction, result conversion, and exception handling.
5. It does not alter runtime behavior, side-effect policy, artifact schemas, or public CLI output.
6. `git diff --check` passes.
7. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent/adapters/native_web.py` passes.
8. Focused tests pass:
   - Worker J: `tests.test_breakpoint_manager` plus any paused-session related existing tests the worker identifies.
   - Worker K: closure wrapper / hook related tests, or at minimum full `tests.test_native_web` / targeted native-web compatible tests if available.
9. The worker reports exact validation commands.

## Expected merge order

1. Worker J: paused-session dispatch extraction.
2. Worker K: closure/runtime hook dispatch extraction.

If Worker K conflicts after Worker J lands, the main agent should rebase / resolve only the narrow `apply_minimal_protection` call placement and helper insertion, preserving both workers' assigned branch order.

## Completion definition for this rollout

This rollout is complete only when:

- All accepted worker PRs are reviewed and merged into `refactor/consolidate-hooks-native-web`.
- The branch is pushed to `origin/refactor/consolidate-hooks-native-web`.
- `git status --short --branch` is clean except ignored local artifacts.
- `git diff --check` passes.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests` passes.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v` passes, or any failure is explicitly attributed to an external service gate outside the pure-Python test suite.
- ROADMAP / status docs are updated to reflect B3c progress.

## Execution result

Pending worker PRs.

## Final validation status

Pending worker PR review, merge, and full validation.
