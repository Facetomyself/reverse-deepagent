# Multi-agent rollout 6: async chunk and module-tail dispatch extraction

Date: 2026-06-12
Base branch: `refactor/consolidate-hooks-native-web`
Coordinator: main agent

## Objective

Continue the B3c refactor after rollout 5 by reducing the remaining branch density
inside `NativeWebRuntime.apply_minimal_protection(...)` without changing runtime
behavior, artifact schemas, side-effect boundaries, BrowserProvider behavior, or
legacy MCP compatibility boundaries.

Rollout 5 left `apply_minimal_protection(...)` at 1555 lines / 22 branch
predicates. Rollout 6 targets the next two branch groups while preserving the
existing final fallback hook behavior.

## Current baseline

Latest local baseline before rollout 6:

- `apply_minimal_protection`: lines 531-2085, 1555 lines.
- Remaining branch predicates in `apply_minimal_protection`: 22.
- Extracted helpers already present:
  - `_dispatch_module_federation(...)`
  - `_dispatch_custom_loader(...)`
  - `_dispatch_paused_session(...)`
  - `_dispatch_closure_runtime(...)`
  - `_dispatch_heap(...)`
  - `_dispatch_closure_prefix(...)`
  - `_dispatch_object_graph(...)`
- Open GitHub PRs at coordination start: none.

## Worker split

### Worker N: Async chunk dispatch extraction

Branch: `codex/b3c-async-chunk-dispatch`
Worktree: `/Users/mengma/reverse/reverse_agent_worktrees/b3c-async-chunk-dispatch`
Owned file:

- `src/reverse_deepagent/adapters/native_web.py`

Task:

- Extract the contiguous async chunk traversal / load / module-hook branch group
  from `apply_minimal_protection(...)` into:

```python
def _dispatch_async_chunk(
    self,
    protection_name: str,
    context: dict,
    page: Any,
) -> ProtectionResult | None:
    ...
```

Expected source range starts at
`_is_async_chunk_recursive_traversal_plan_request(...)` and runs through
`_is_async_chunk_module_hook_request(...)`, stopping before
`_is_custom_loader_module_hook_request(...)`. Preserve current order and semantics.
Do not extract async / custom module-diff tail in this worker.

Required local validation before PR:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent/adapters/native_web.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_native_web_runtime -v
```

### Worker O: Module tail dispatch extraction

Branch: `codex/b3c-module-tail-dispatch`
Worktree: `/Users/mengma/reverse/reverse_agent_worktrees/b3c-module-tail-dispatch`
Owned file:

- `src/reverse_deepagent/adapters/native_web.py`

Task:

- Extract the tail branch group from `apply_minimal_protection(...)` into:

```python
def _dispatch_module_tail(
    self,
    protection_name: str,
    context: dict,
    page: Any,
) -> ProtectionResult | None:
    ...
```

Expected source range starts at
`_is_custom_loader_module_hook_request(...)` and includes
`_is_async_chunk_module_diff_request(...)`, `_is_custom_loader_module_diff_request(...)`,
`_is_module_discovery_request(...)`, `_is_module_hook_request(...)`, and
`_is_breakpoint_request(...)`. Preserve current order and semantics. Do not move or
refactor the final fallback hook behavior after the breakpoint branch.

Required local validation before PR:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent/adapters/native_web.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_native_web_runtime -v
```

## Integration order

Both workers edit `src/reverse_deepagent/adapters/native_web.py`; conflicts are
expected. Preferred order:

1. Merge Worker N / async chunk first.
2. Rebase or replay Worker O / module tail on top of the updated base.
3. Run focused tests after each merge.
4. Run final validation before closing rollout:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
```

## Invariants

- Do not change public artifact schema names.
- Do not change side-effect policy semantics.
- Do not start browsers, connect CDP, or call MCP as part of this refactor.
- Preserve final fallback hook behavior in `apply_minimal_protection(...)`.
- Do not touch Android / iOS / mini-program runtime chains.
- Do not move workspace canonical paths.

## Completion evidence to record

- PR number, branch, merge commit, and validation commands for each worker.
- Updated line / branch count for `apply_minimal_protection(...)` after merges.
- Final test result summary.
- ROADMAP update noting B3c progress and remaining branch families.

## Execution result

Status: completed for rollout 6.

Merged PRs:

| Worker | PR | Branch | Scope | Merge commit | Notes |
|---|---:|---|---|---|---|
| N | #34 | `codex/b3c-async-chunk-dispatch` | Extracted async chunk traversal / load / module-hook branch family into `_dispatch_async_chunk(...)` | `a45760d1b4e676c8443d3121da38e6d621452dc0` | Worker used GitHub API for the remote commit after Git HTTPS flaked; main agent verified remote tree, reran focused tests, then merged. |
| O | #35 | `codex/b3c-module-tail-dispatch` | Extracted custom-loader module-hook, async/custom module-diff, module discovery, generic module hook, and breakpoint tail into `_dispatch_module_tail(...)` | `7a6c55d20e883582dd5aae1185d632f85253dddd` | Worker replayed on top of PR #34; main agent verified fallback hook remained in `apply_minimal_protection(...)`, reran focused tests, then merged. |

Validation performed by the main agent:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent/adapters/native_web.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_native_web_runtime -v
```

Focused validation result after each merge:

```text
Ran 204 tests
OK
```

Final rollout 6 dispatch stats:

```text
apply_minimal_protection lines 531-954 count 424
_dispatch_module_tail lines 956-1432 count 477
_dispatch_async_chunk lines 1434-2107 count 674
_dispatch_module_federation lines 2109-3003 count 895
_dispatch_custom_loader lines 8334-9193 count 860
_dispatch_paused_session lines 9195-9889 count 695
_dispatch_closure_runtime lines 9891-10686 count 796
_dispatch_heap lines 10688-12269 count 1582
_dispatch_closure_prefix lines 14253-14406 count 154
_dispatch_object_graph lines 14408-14472 count 65
apply_minimal_protection branch predicates: 6
```

Progress compared with rollout 6 baseline:

- `apply_minimal_protection`: 1555 lines -> 424 lines.
- Branch predicates in `apply_minimal_protection`: 22 -> 6.
- New helpers added:
  - `_dispatch_async_chunk(...)`
  - `_dispatch_module_tail(...)`

Side-effect boundary remained unchanged:

- No public artifact schema names changed.
- No side-effect policy semantics changed.
- No browser / CDP / MCP action was added as part of the refactor.
- Android / iOS / mini-program runtime chains were not touched.
- Workspace canonical paths were not moved.
- Final fallback hook behavior remains in `apply_minimal_protection(...)`.

## Remaining B3c follow-up

After rollout 6, `apply_minimal_protection(...)` still owns the first six branch
families plus the final fallback hook:

1. MutationObserver timeline.
2. Object-root mutation audit.
3. Heap snapshot collect.
4. Runtime object graph diff.
5. Page mutation audit.
6. Recursive continuation readiness.
7. Final fallback hook install / snapshot.

The next safe extraction pass should consider a small front-of-function helper for
timeline / mutation / graph review-only branches, while keeping the final fallback
hook behavior in the main function until a dedicated fallback dispatch contract is
reviewed.
