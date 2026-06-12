# Multi-agent rollout 10: native-web default fallback helper extraction

Date: 2026-06-12

Base branch: `refactor/consolidate-hooks-native-web`

Status: planned / dispatching

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
