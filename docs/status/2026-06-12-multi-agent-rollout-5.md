# Multi-agent rollout 5: native Web protection dispatch extraction

Date: 2026-06-12
Base branch: `refactor/consolidate-hooks-native-web`
Coordinator: main agent

## Objective

Continue the B3c refactor by reducing the size and branch density of
`NativeWebRuntime.apply_minimal_protection(...)` without changing runtime behavior,
artifact schemas, side-effect boundaries, or BrowserProvider / MCP architecture.

Rollout 4 extracted paused-session and closure-runtime branch groups. Rollout 5
focuses on the next two contiguous branch families:

1. Module Federation recursive traversal / export hook dispatch.
2. Custom loader traversal / execution / continuation dispatch.

## Current baseline

Latest local baseline before rollout 5:

- `apply_minimal_protection`: lines 531-3826, 3296 lines.
- Extracted helpers already present:
  - `_dispatch_paused_session(...)`
  - `_dispatch_closure_runtime(...)`
  - `_dispatch_heap(...)`
  - `_dispatch_closure_prefix(...)`
  - `_dispatch_object_graph(...)`
- Remaining branch predicates in `apply_minimal_protection`: 47.
- Open GitHub PRs at coordination start: none.

## Worker split

### Worker L: Module Federation dispatch extraction

Branch: `codex/b3c-module-federation-dispatch`
Worktree: `/Users/mengma/reverse/reverse_agent_worktrees/b3c-module-federation-dispatch`
Owned file:

- `src/reverse_deepagent/adapters/native_web.py`

Task:

- Extract the Module Federation branch group from `apply_minimal_protection(...)` into:

```python
def _dispatch_module_federation(
    self,
    protection_name: str,
    context: dict,
    page: Any,
) -> ProtectionResult | None:
    ...
```

Expected source branch family includes the predicates from
`_is_module_federation_recursive_continuation_checkpoint_request(...)` through the
Module Federation `get_init` / export hook plan and install handling, preserving
current order and semantics.

Required local validation before PR:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent/adapters/native_web.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_native_web_runtime -v
```

### Worker M: Custom loader dispatch extraction

Branch: `codex/b3c-custom-loader-dispatch`
Worktree: `/Users/mengma/reverse/reverse_agent_worktrees/b3c-custom-loader-dispatch`
Owned file:

- `src/reverse_deepagent/adapters/native_web.py`

Task:

- Extract the custom-loader branch group from `apply_minimal_protection(...)` into:

```python
def _dispatch_custom_loader(
    self,
    protection_name: str,
    context: dict,
    page: Any,
) -> ProtectionResult | None:
    ...
```

Expected source branch family includes the predicates from
`_is_custom_loader_continuation_execution_request(...)` through
`_is_custom_loader_traversal_request(...)`, preserving current order and semantics.

Required local validation before PR:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent/adapters/native_web.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_native_web_runtime -v
```

## Integration order

Because both workers edit `src/reverse_deepagent/adapters/native_web.py`, expect
merge conflicts. Preferred integration order:

1. Merge Worker L / Module Federation first.
2. Rebase or replay Worker M / custom-loader extraction on top of the updated base.
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
