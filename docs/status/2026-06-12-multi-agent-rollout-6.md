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
