# Native Web Final Fallback Hook Dispatch Contract

## 1. Scope

This document defines the Rollout 8 contract for extracting the final fallback hook
install / snapshot path from `NativeWebRuntime.apply_minimal_protection(...)` into a
small dispatch helper. It is a contract-first design note for a future code PR; it
does not authorize behavior changes, artifact migration, or new runtime capability
wiring.

The target code path is the default Native Web hook fallback reached after all
specific protection dispatch helpers decline a request by returning `None`. Today
that fallback is still implemented inline at the tail of
`apply_minimal_protection(...)` even though Rollout 7 already reduced that method to
roughly 85 lines and removed request-branch predicates from the main method.

## 2. Current state and goal

### Current state

`NativeWebRuntime.apply_minimal_protection(...)` currently behaves as a thin dispatch
chain:

1. Normalize `context` to `{}`.
2. Ask request-specific helpers such as source, paused, heap, timeline, object graph,
   observation review, module federation, custom loader, async chunk, and module tail
   dispatchers whether they own the request.
3. Return immediately when a helper returns a `ProtectionResult`.
4. Ensure a browser session / page before helpers that require a live page.
5. If every concrete helper returns `None`, execute the inline final fallback:
   instantiate `BrowserHookManager`, call `install(page)`, call `snapshot(page)`, and
   build the legacy hook timeline `ProtectionResult`.

The inline fallback is intentionally broad: a request like `console.clear` that does
not match any specialized helper still installs the baseline Native Web hooks and
returns `virtual://workspace/hook-timeline.json` metadata.

### Goal

Future extraction should move only the final fallback block into a helper, for
example `_dispatch_default_hook_fallback(...)`, while preserving the observable
behavior of `apply_minimal_protection(...)` for no-match requests and install
failures.

The extraction goal is readability and dispatch-chain consistency, not a new feature.
After extraction, the main method should still read as: specific dispatchers first,
then exactly one default fallback dispatcher at the end.

## 3. Non-negotiable invariants

### Fallback entry condition

The fallback helper may run only when all concrete dispatch helpers have returned
`None` for the same `protection_name` and `context`.

Concretely, the future main method must preserve this gate:

```python
result = self._dispatch_module_tail(protection_name, context, page)
if result is not None:
    return result
return self._dispatch_default_hook_fallback(protection_name, context, page)
```

It must not call the fallback helper before any existing concrete helper has had a
chance to accept the request. It must not call fallback in addition to a successful
concrete dispatch. If a concrete helper returns a `ProtectionResult` with
`status=failed`, that failed result is still authoritative and must not be replaced by
the default fallback.

### Hook manager behavior

The fallback must continue to use the current baseline hook manager calls:

```python
hooks = BrowserHookManager()
install = hooks.install(page)
snapshot = hooks.snapshot(page)
```

The extraction must not swap in a different manager, use provider-specific hook APIs,
introduce CDP hook installation, or make installation conditional on a new capability
flag unless a later, separately reviewed contract changes the baseline semantics.

### Result compatibility

For the same inputs and fake provider behavior, the helper must preserve the current
`ProtectionResult` shape:

- `protection_name` remains the caller-provided name.
- `applied_actions` remains `install_hook:<hook_name>` for enabled installed hooks.
- If `install.ok` is true and no concrete hook action was enabled,
  `applied_actions` remains `['install_hook:runtime_baseline']`.
- `verification` continues to include:
  - `hook_install_ok=<bool>`
  - `hook_event_count=<snapshot.event_count>`
  - `context_keys=<sorted context keys>`
  - `hook_install_error=<install.error>` only when `install.error` is present
- `status` remains `ExecutionStatus.SUCCESS` when `install.ok` is true, otherwise
  `ExecutionStatus.FAILED`.
- `artifacts` continues to contain the hook timeline artifact at
  `virtual://workspace/hook-timeline.json`.
- Artifact kind remains `ArtifactKind.JSON`.
- Artifact description remains compatible with the existing Native Web hook timeline
  wording.
- Artifact metadata continues to include at least:
  - `event_count`
  - `installed`
  - `protection_name`
- `next_action` remains `resume_recon` on success and
  `ensure_browser_provider_or_hook_capability` on install failure.
- `confidence` remains `ConfidenceLevel.MEDIUM` on success and `ConfidenceLevel.LOW`
  on install failure.

The compatibility target is behavioral equivalence, not only type equivalence. Tests
should compare values that downstream coordinators, workspace consumers, and existing
fixtures can observe.

## 4. Dispatch order and side-effect boundary

### Required call order

The final fallback extraction must preserve the current order:

1. Dispatch helpers that do not require an ensured page.
2. `_ensure_session()` / active page lookup / `new_page()` fallback.
3. Dispatch helpers that require a page.
4. Recursive continuation readiness dispatch.
5. Module federation dispatch.
6. Custom loader dispatch.
7. Async chunk dispatch.
8. Module tail dispatch.
9. Default fallback hook install / snapshot helper.

The fallback helper receives a `page` that was already acquired by the main method.
It must not call `_ensure_session()` itself in the initial extraction. Keeping session
acquisition outside the helper avoids changing the existing browser-provider failure
surface and preserves the current `ensure_browser_provider` failure result that is
returned before page-dependent dispatchers run.

### Side-effect boundary

The fallback helper is allowed to perform only the side effects already present in
the inline fallback:

- instantiate `BrowserHookManager()`;
- call `install(page)`;
- call `snapshot(page)`;
- construct and return a `ProtectionResult`.

It must not add any of the following:

- new browser navigation;
- new page creation;
- new CDP session attachment;
- new CDP commands;
- new MCP / legacy MCP calls;
- Android, iOS, mini-program, or other mobile runtime behavior;
- provider registry mutation;
- workspace file writes;
- artifact schema changes;
- artifact path moves;
- backend manifest mutation;
- dual-write or foldered-canonical workspace behavior;
- retries, waits, sleeps, timers, or background tasks.

This means the helper is a pure extraction around existing hook-manager calls. It may
observe the hook manager results and format them into the same result object, but it
may not broaden runtime reach.

## 5. Proposed helper signature and return contract

The preferred future helper shape is:

```python
def _dispatch_default_hook_fallback(
    self,
    protection_name: str,
    context: dict[str, Any],
    page: Any,
) -> ProtectionResult:
    """Install baseline Native Web hooks after every concrete dispatcher declined."""
```

Return contract:

- Always returns a `ProtectionResult`.
- Never returns `None`; it is the terminal fallback, not another optional matcher.
- Does not decide whether the request is eligible for fallback. Eligibility is owned
  by the caller via dispatch-chain ordering.
- Does not catch or translate browser session acquisition errors, because `page` is a
  required input and session acquisition has already happened.
- Should keep hook install / snapshot exceptions behavior equivalent to the current
  inline block. If the inline block currently allows an exception from
  `BrowserHookManager().install(page)` or `.snapshot(page)` to escape, the helper must
  not silently convert it into a failed `ProtectionResult` during this extraction.
- Should keep local variable naming boring and traceable (`hooks`, `install`,
  `snapshot`, `applied_actions`, `verification`, `status`) so diff review can prove
  this is a move-only extraction.

A secondary option is an explicitly optional dispatcher signature:

```python
def _dispatch_default_hook_fallback(
    self,
    protection_name: str,
    context: dict[str, Any],
    page: Any,
) -> ProtectionResult | None:
    ...
```

That option is discouraged for Rollout 8 because it blurs the contract. The fallback
is terminal. Returning `None` would create a new unresolved tail state that does not
exist today.

## 6. Suggested implementation outline for the future code PR

The future code PR should be intentionally small:

1. Add `_dispatch_default_hook_fallback(...)` near the other Native Web dispatch
   helpers.
2. Move the current inline fallback block into the helper without changing result
   fields.
3. Replace the tail of `apply_minimal_protection(...)` with:

   ```python
   return self._dispatch_default_hook_fallback(protection_name, context, page)
   ```

4. Add focused tests proving the dispatch boundary.
5. Avoid any cleanup that is not required for the extraction.

Design note: this fallback is the default path, not an edge path. Rollout 8
should treat the extraction as move-only plumbing: lock behavior first, then defer
any future hook-manager abstraction to a separately reviewed contract.

## 7. Test requirements for the future extraction

The future code PR should add or preserve focused unit tests in
`tests/test_native_web_runtime.py`. Full test names can vary, but coverage should
prove the following behaviors.

### No-match fallback remains equivalent

A request that matches no concrete helper, for example the existing `console.clear`
case, should still:

- return `status.value == 'success'` when hook installation succeeds;
- include `install_hook:fetch_xhr` or the equivalent enabled baseline hook action from
  the fake hook manager behavior;
- return `next_action == 'resume_recon'`;
- return artifact path `virtual://workspace/hook-timeline.json`;
- include hook timeline metadata with `event_count`, `installed`, and
  `protection_name`.

The test should fail if the helper returns `None`, skips `snapshot(page)`, changes the
artifact path, or changes the success next action.

### Install failure remains equivalent

A fake page / provider setup that causes `BrowserHookManager().install(page)` to
return `ok=False` and an error should still produce:

- `status.value == 'failed'`;
- `next_action == 'ensure_browser_provider_or_hook_capability'`;
- `confidence.value == 'low'`;
- `verification` containing `hook_install_ok=False`;
- `verification` containing `hook_install_error=<same error>`;
- hook timeline artifact path unchanged.

The test should specifically guard against swallowing the error, changing it to a
browser-provider failure, or skipping the artifact on install failure.

### Concrete requests must not fall through to fallback

At least one representative concrete request should prove that a non-`None` dispatch
helper result prevents fallback execution. Good candidates are existing stable tests
for `hook-function`, module discovery, source-map follow-through, or module tail
requests.

The assertion should focus on observable behavior:

- the concrete request returns its concrete artifact path, such as
  `virtual://workspace/function-hooks.json`, not `virtual://workspace/hook-timeline.json`
  as the primary artifact;
- `applied_actions` contains the concrete action, such as
  `install_function_hook:<name>`, not the baseline fallback action;
- `next_action` remains the concrete helper next action.

If implementation uses mocking or monkeypatching, it may also assert that
`_dispatch_default_hook_fallback(...)` was not invoked, but observable result checks
should remain the primary guard.

### Browser-provider failure surface remains outside fallback

A provider/session setup that fails before page acquisition should still return the
current browser-provider unavailable result from `apply_minimal_protection(...)`:

- `status.value == 'failed'`;
- `next_action == 'ensure_browser_provider'`;
- `verification` includes `Native Web browser provider unavailable: ...`;
- fallback hook installation is not attempted.

This protects the contract that the fallback helper receives an already acquired
`page` and does not own `_ensure_session()`.

## 8. Rollback and risk points

The default fallback is sensitive because it catches every no-match protection
request. A bad extraction can quietly alter the default behavior even when all
specialized helper tests still pass.

Risk points to watch:

- accidentally calling fallback before a concrete helper;
- calling fallback after a concrete helper returned a failed `ProtectionResult`;
- moving `_ensure_session()` into the helper and changing provider failure semantics;
- converting hook install / snapshot exceptions into a new result shape;
- changing artifact path, kind, metadata keys, `next_action`, or `confidence`;
- adding CDP / MCP / mobile behavior under the generic fallback name;
- making fallback optional and creating a new `None` tail state.

Rollback should be straightforward if Rollout 8 stays small: revert the helper
extraction commit and restore the inline fallback block. Do not pair this extraction
with larger hook-manager, workspace, or provider refactors; otherwise rollback stops
being surgical.

## 9. Recommended follow-up rollouts

1. **Rollout 8 code PR:** implement only `_dispatch_default_hook_fallback(...)` and the
   focused tests listed above.
2. **Rollout 9 audit:** after extraction lands, audit all `apply_minimal_protection(...)`
   dispatch helper names and ordering comments for readability, without changing
   behavior.
3. **Later hook-manager contract:** if Native Web needs capability-gated hook managers
   or provider-specific hook installation, write a separate contract first. That work
   should explicitly revisit artifact compatibility and side-effect boundaries instead
   of piggybacking on the fallback extraction.
4. **Workspace compatibility review:** only if a later rollout changes hook timeline
   artifact contents, update workspace / manifest contract tests and runtime docs in
   the same PR. Rollout 8 itself must not move `virtual://workspace/hook-timeline.json`.
