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

Status: completed for rollout 7.

## Execution result

Merged PRs:

| Worker | PR | Branch | Scope | Merge commit | Notes |
| --- | ---: | --- | --- | --- | --- |
| P | #37 | `codex/b3c-observation-review-dispatch` | Extracted MutationObserver timeline, object-root mutation audit, heap snapshot collect, runtime object graph diff, and page mutation audit into `_dispatch_observation_review(...)` | `7dfd17e2` | Main agent reviewed the PR, reran focused validation, merged first, and verified the final fallback hook remained in `apply_minimal_protection(...)`. |
| Q | #36 | `codex/b3c-recursive-readiness-dispatch` | Extracted recursive continuation readiness into `_dispatch_recursive_continuation_readiness(...)` | `4dfebcd2` | Worker used GitHub Git Data API for the remote PR commit after Git HTTPS flaked; main agent merged after #37, reran focused validation, and verified dispatch order. |

Focused validation after each merge:

```text
git diff --check
compileall src/reverse_deepagent/adapters/native_web.py
python -m unittest tests.test_native_web_runtime -v
Ran 204 tests
OK
```

Final rollout 7 dispatch stats:

```text
apply_minimal_protection lines 531-615 count 85
_dispatch_observation_review lines 8930-9209 count 280
_dispatch_recursive_continuation_readiness lines 1770-1842 count 73
_dispatch_module_tail lines 617-1093 count 477
_dispatch_async_chunk lines 1095-1768 count 674
_dispatch_module_federation lines 1844-2738 count 895
_dispatch_custom_loader lines 8069-8928 count 860
_dispatch_paused_session lines 9211-9905 count 695
_dispatch_closure_runtime lines 9907-10702 count 796
_dispatch_heap lines 10704-12285 count 1582
_dispatch_source lines 2740-6591 count 3852
apply_minimal_protection request branch predicates: 0
fallback hook remains in apply_minimal_protection: true
```

Final full validation:

```text
git diff --check
compileall src/reverse_deepagent tests
python -m unittest discover -s tests -v
Ran 1747 tests in 71.585s
OK (skipped=2)
```

Progress compared with rollout 7 baseline:

- `apply_minimal_protection`: 424 lines -> 85 lines.
- Request branch predicates in `apply_minimal_protection`: 6 -> 0.
- New helpers added:
  - `_dispatch_observation_review(...)`
  - `_dispatch_recursive_continuation_readiness(...)`

Side-effect boundary remained unchanged:

- No public artifact schema names changed.
- No side-effect policy semantics changed.
- No browser / CDP / MCP action was added as part of the refactor.
- Android / iOS / mini-program runtime chains were not touched.
- Workspace canonical paths were not moved.
- Final fallback hook behavior remains in `apply_minimal_protection(...)`.

## Remaining follow-up after rollout 7

B3c branch extraction is complete for `apply_minimal_protection(...)`: the method no
longer owns direct request branch predicates. Remaining refactor follow-ups are now
separate items:

1. Review a dedicated final fallback hook dispatch contract before moving the
   fallback install / snapshot block out of the main method.
2. Plan the next large dispatch decomposition around `_dispatch_source(...)`,
   which remains the largest helper.
3. Triage the untracked readonly audit report separately; it was not staged or
   committed as part of this rollout.
