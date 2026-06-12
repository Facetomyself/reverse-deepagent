# Multi-agent rollout 7: final native Web protection front dispatch extraction

## Purpose

Continue the B3c refactor after rollout 6 by removing the remaining request
branch predicates from `NativeWebRuntime.apply_minimal_protection(...)` without
changing runtime behavior, public artifact schemas, side-effect policy, browser
provider semantics, or legacy MCP compatibility.

Rollout 6 left `apply_minimal_protection(...)` at 424 lines with 6 request
branch predicates. The final fallback hook install / snapshot behavior remains
inside the main method until a dedicated fallback dispatch contract is reviewed.

## Baseline

Latest local baseline before rollout 7:

- Branch: `refactor/consolidate-hooks-native-web`.
- Local / upstream divergence: `0 0`.
- Open PRs: none.
- Untracked local file intentionally excluded from this rollout:
  `docs/status/2026-06-12-readonly-code-audit.md`.
- `apply_minimal_protection`: lines 531-954, 424 lines.
- Remaining request branch predicates in `apply_minimal_protection`: 6.
- `_dispatch_observation_review(...)`: missing.
- `_dispatch_recursive_continuation_readiness(...)`: missing.

Remaining request families in the main method:

1. MutationObserver timeline.
2. Object-root mutation audit.
3. Heap snapshot collect.
4. Runtime object graph diff.
5. Page mutation audit.
6. Recursive continuation readiness.
7. Final fallback hook install / snapshot remains in the main method.

## Worker assignments

### Worker P: observation review dispatch

Branch:

```text
codex/b3c-observation-review-dispatch
```

Owned file:

```text
src/reverse_deepagent/adapters/native_web.py
```

Task:

- Extract only the first five front review branch families into:

```python
def _dispatch_observation_review(
    self,
    protection_name: str,
    context: dict,
    page: Any,
) -> ProtectionResult | None:
    ...
```

Owned branch families:

- MutationObserver timeline.
- Object-root mutation audit.
- Heap snapshot collect.
- Runtime object graph diff.
- Page mutation audit.

Do not touch:

- Recursive continuation readiness.
- `_dispatch_paused_session(...)`.
- `_dispatch_closure_runtime(...)`.
- `_dispatch_module_federation(...)`.
- `_dispatch_custom_loader(...)`.
- `_dispatch_async_chunk(...)`.
- `_dispatch_module_tail(...)`.
- Final fallback hook install / snapshot.
- Public artifact schema names or side-effect policy semantics.

### Worker Q: recursive continuation readiness dispatch

Branch:

```text
codex/b3c-recursive-readiness-dispatch
```

Owned file:

```text
src/reverse_deepagent/adapters/native_web.py
```

Task:

- Extract only the recursive continuation readiness branch into:

```python
def _dispatch_recursive_continuation_readiness(
    self,
    protection_name: str,
    context: dict,
) -> ProtectionResult | None:
    ...
```

- Keep the call site after `_dispatch_closure_runtime(...)` and before
  `_dispatch_module_federation(...)`, preserving existing branch ordering.

Do not touch:

- Observation review branches.
- Module Federation / custom-loader / async chunk / module-tail helpers.
- Final fallback hook install / snapshot.
- Public artifact schema names or side-effect policy semantics.

## Merge order

1. Merge Worker P first.
2. Rebase / replay Worker Q on top of Worker P if the call-site context
   conflicts.
3. Run focused validation after each merge.
4. Run full validation before closing the rollout.
5. Update this document and `ROADMAP.md` with final line / predicate counts.

## Validation commands

Worker-focused validation:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent/adapters/native_web.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_native_web_runtime -v
```

Final rollout validation:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
```

## Completion definition

This rollout is complete only when:

- Both worker PRs are merged into `refactor/consolidate-hooks-native-web`.
- `apply_minimal_protection(...)` has no direct request branch predicates for
  the six extracted B3c families.
- Final fallback hook install / snapshot behavior remains in
  `apply_minimal_protection(...)`.
- Focused and full validation pass.
- `ROADMAP.md` and this status document reflect the final state.

## Current status

Status: in progress.
