# Multi-agent rollout 10: native-web default fallback helper extraction

Date: 2026-06-12

Base branch: `refactor/consolidate-hooks-native-web`

Status: completed

## Objective

Rollout 10 implements the contract documented in
`docs/runtime/native-web-fallback-dispatch-contract.md`: extract the final default
Native Web hook fallback from `NativeWebRuntime.apply_minimal_protection(...)` into a
small helper without changing observable behavior.

This rollout is intentionally narrow. It is a readability / dispatch-chain consistency
change, not a new runtime capability.

## Current baseline evidence

- `apply_minimal_protection(...)` has no direct request branch predicates, but its
  terminal no-match fallback still lives inline at the end of the method.
- The inline fallback currently:
  - instantiates `BrowserHookManager()`;
  - calls `install(page)`;
  - calls `snapshot(page)`;
  - formats the existing `virtual://workspace/hook-timeline.json` result.
- Existing tests cover successful no-match fallback and representative concrete hook
  installation, but do not yet lock install-failure behavior or provider-failure
  outside-fallback behavior as focused regression tests.

## Worker split

### Worker X: fallback helper extraction

Branch: `codex/rollout10-fallback-helper`

Owned files:

- `src/reverse_deepagent/adapters/native_web.py`
- `tests/test_native_web_runtime.py`

Responsibilities:

1. Add `_dispatch_default_hook_fallback(self, protection_name, context, page) -> ProtectionResult`.
2. Move the existing inline fallback block into that helper without changing result
   fields, status mapping, artifact path, metadata, verification strings, next action,
   or confidence.
3. Replace the tail of `apply_minimal_protection(...)` with exactly one call to the
   helper after `_dispatch_module_tail(...)` returns `None`.
4. Add focused tests for:
   - no-match fallback success remains equivalent;
   - hook install failure remains equivalent;
   - concrete request result does not fall through to fallback;
   - browser-provider/session acquisition failure remains outside fallback.
5. Keep the patch small and move-only. No hook-manager abstraction, no provider
   capability gates, no workspace path or schema changes.

Out of scope:

- Do not change `BrowserHookManager` behavior.
- Do not add CDP / MCP / mobile behavior.
- Do not move `_ensure_session()` into the fallback helper.
- Do not alter artifact keys, workspace paths, or backend manifest semantics.

## Main-agent review checklist

Before merge, the main agent must verify:

- `apply_minimal_protection(...)` still calls all existing concrete dispatch helpers
  before the default fallback helper.
- `_dispatch_default_hook_fallback(...)` never returns `None`.
- Concrete failed `ProtectionResult` values are not replaced by fallback.
- Fallback success keeps:
  - `next_action == "resume_recon"`;
  - `virtual://workspace/hook-timeline.json`;
  - hook install / snapshot verification fields.
- Fallback install failure keeps:
  - `next_action == "ensure_browser_provider_or_hook_capability"`;
  - `confidence == LOW`;
  - `hook_install_error=<same error>` when present.
- Provider/session acquisition failure still returns `next_action == "ensure_browser_provider"`
  before fallback can run.

## Validation commands

Focused validation:

```bash
git diff --check
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

- `_dispatch_default_hook_fallback(...)` exists and owns the terminal fallback block.
- `apply_minimal_protection(...)` has no inline fallback block after module-tail
  dispatch; it calls the helper instead.
- Focused tests cover success, install failure, no fallthrough from concrete dispatch,
  and provider failure outside fallback.
- No workspace paths, artifact schema names, BrowserProvider lifecycle behavior, CDP,
  MCP, Android, iOS, or mini-program runtime behavior are changed.
- Worker PR is merged, final validation passes, and `ROADMAP.md` plus this status
  document reflect the final state.

## Completion result

Rollout 10 is complete.

Merged worker PR:

| Worker | PR | Branch | Merge commit | Scope |
| --- | ---: | --- | --- | --- |
| X | [#44](https://github.com/Facetomyself/reverse-deepagent/pull/44) | `codex/rollout10-fallback-helper` | `90ae154e09c3e556e632182f60cd6f872d133e2d` | Extracted `_dispatch_default_hook_fallback(...)` from `NativeWebRuntime.apply_minimal_protection(...)` and added focused fallback boundary tests. |

Implementation summary:

- `NativeWebRuntime._dispatch_default_hook_fallback(...)` now owns the terminal
  default Native Web hook install / snapshot path.
- `apply_minimal_protection(...)` now reaches the fallback only after
  `_dispatch_module_tail(...)` returns `None` and then calls the helper exactly once.
- The helper receives an already acquired `page`; session acquisition and provider
  failure handling remain outside the fallback helper.
- The fallback still uses `BrowserHookManager().install(page)` followed by
  `BrowserHookManager().snapshot(page)` behavior through the same manager instance.
- The canonical fallback artifact remains `virtual://workspace/hook-timeline.json`.

Behavior locked by focused tests:

- no-match fallback success keeps `next_action == "resume_recon"`, hook install /
  snapshot verification fields, context-key reporting, and hook timeline metadata;
- hook install failure keeps `next_action == "ensure_browser_provider_or_hook_capability"`,
  low confidence, no applied actions, and the original install error in verification;
- concrete hook requests do not fall through to the default fallback;
- browser provider / session acquisition failures return `ensure_browser_provider`
  before the fallback helper can run.

Runtime / side-effect boundary:

- No workspace path, artifact schema, backend manifest, dual-write, or
  foldered-canonical behavior changed.
- No BrowserProvider lifecycle behavior changed beyond preserving the existing page
  acquisition boundary.
- No CDP, MCP, Android, iOS, mini-program, navigation, retry, wait, or background
  behavior was added.

Final validation on `refactor/consolidate-hooks-native-web` after PR #44 merge:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_native_web_runtime -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
PATH="/Users/mengma/reverse/reverse_agent/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
```

Observed result:

- `tests.test_native_web_runtime`: 206 tests, OK.
- `compileall`: OK.
- Full `unittest discover -s tests -v`: 1758 tests, OK, 2 skipped.

## Follow-up priorities after rollout 10

1. **P1 `_dispatch_source(...)` staged decomposition**: start with the safest
   route-shell / review-evidence extraction batch from
   `docs/plans/2026-06-12-source-dispatch-decomposition-plan.md`.
2. **P1 Chrome launcher hardening continuation**: validate numeric ports / waits,
   resolve `CHROME_PATH` vs `CHROME_APP_NAME` authority, and add shell validation
   tests without turning the script into a broad launcher framework.
3. **P2 README / active-doc legacy alias cleanup**: keep deprecated `mcp` /
   `jsreverser-mcp` examples only where explicitly testing compatibility.
