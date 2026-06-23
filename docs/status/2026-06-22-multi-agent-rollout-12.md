# Multi-agent rollout 12: structural debt reduction wave 1

Date: 2026-06-22

Base branch: `refactor/consolidate-hooks-native-web`

Status: completed (2026-06-22, 1765 tests OK)

## Objective

Rollout 12 starts the next wave after rollout 11 closure. Focus: P1 structural debt
from the 2026-06-15 review, prioritized by risk/reward ratio. Platform Expansion
is explicitly deferred per user directive.

The main agent coordinates, reviews, merges, and runs final validation. Workers
own bounded implementation slices on separate branches and PRs.

## Pre-flight scouting results

| Item | File | Current state | Scope |
|---|---|---|---|
| S2-S7 source dispatch | `native_web.py` (14317 lines) | 34 dispatch branches remain in `_dispatch_source` (3665 lines); S1 extracted only 3 | Extract next ~8-10 review-only / read-only branches |
| B-1 coordinator | `coordinator.py` (2212 lines) | MockJSReverserBridge (223 lines) + Chrome lifecycle (~70 lines) + factories (~120 lines) + registry (~300 lines) + manifest (~300 lines) | Phase 1: extract MockJSReverserBridge + Chrome lifecycle |
| B-2 journal loader | `artifact_tools.py` (13842 lines) | 32 `_load_or_read_workspace_*` functions with identical (data, error, input) loading pattern | Extract common `_load_workspace_journal` helper |
| B-3 bare except | `page_mutation.py` (9509 lines) | 11 bare `except Exception:` blocks; 1 pure `pass`, 10 have minimal fallback values | Add `logger.debug(exc_info=True)` to all 11 sites |
| B-5 internal-registry | — | **Not found in current codebase** — `create_internal_registry_external_delivery_provider` and `InternalRegistry` do not exist in `src/` | Skipped; re-check after external plugin packages are located |
| B-6 README | `README.md` (1332 lines) | Partially addressed in rollout 11; full convergence deferred | Deferred to rollout 13+ |

## Dispatch matrix

| Worker | Branch | Priority | Scope | Owned files |
|---|---|---|---|---|
| A | `codex/rollout12-source-dispatch-s2` | P1 | `_dispatch_source(...)` S2: extract next ~8-10 review-only / read-only source map evidence branches into `native_web_source_dispatch.py` | `native_web.py`, `native_web_source_dispatch.py`, `test_native_web_runtime.py` |
| B | `codex/rollout12-coordinator-b1-phase1` | P1 | Extract `MockJSReverserBridge` → `runtime/mock_bridge.py`, Chrome lifecycle → `runtime/chrome_lifecycle.py` from coordinator.py | `coordinator.py`, `runtime/mock_bridge.py` (new), `runtime/chrome_lifecycle.py` (new), `test_coordinator.py` |
| C | `codex/rollout12-journal-loader-b2` | P2 | Extract `_load_workspace_journal(artifact_key, artifact_class)` helper, migrate all 32 `_load_or_read_workspace_*` callers | `artifact_tools.py`, `test_artifact_tools.py` |
| D | `codex/rollout12-bare-except-b3` | P2 | Add `logger.debug(exc_info=True)` to 11 bare `except Exception:` blocks in page_mutation.py; add file-level logger | `page_mutation.py`, `test_page_mutation.py` |

## Worker A acceptance criteria (Source Dispatch S2)

- Extract **8-10** read-only / review-only predicate branches from `_dispatch_source` into
  `native_web_source_dispatch.py`, following the S1 gateway pattern.
- Target branches (read-only descriptors and review-only plans): `_is_source_map_readiness_request`,
  `_is_source_map_consumer_action_plan_request`, `_is_source_map_consumer_materialization_request`,
  `_is_source_map_typed_payload_preflight_request`, `_is_source_map_followthrough_review_request`,
  `_is_source_map_followthrough_surface_selection_request`, `_is_source_map_followthrough_chain_readiness_request`,
  `_is_source_map_followthrough_one_step_plan_request`, `_is_source_map_followthrough_dispatch_preflight_request`,
  `_is_source_map_terminal_review_package_request`.
- Dispatch order in `_dispatch_source(...)` unchanged.
- Result payloads preserve artifact paths, metadata, status, confidence, and side-effect policy.
- No browser, CDP, MCP, mobile, workspace path, or backend manifest behavior change.
- Add or update focused native-web / source-map tests covering extracted branches.

## Worker B acceptance criteria (Coordinator B-1 Phase 1)

- `MockJSReverserBridge` (lines 76-299) moves to `reverse_deepagent/runtime/mock_bridge.py`.
- Chrome lifecycle functions (`ensure_chrome_debug` / `stop_chrome_debug` orchestration in `run_reverse_pipeline`) move to `reverse_deepagent/runtime/chrome_lifecycle.py` as a `RuntimeLifecycleManager` or plain helper.
- `coordinator.py` imports from the new modules; behavior unchanged.
- No changes to factory functions, registry, or manifest code (saved for Phase 2).
- Existing `test_coordinator.py` tests pass; add focused tests for moved code.

## Worker C acceptance criteria (Journal Loader B-2)

- Extract a `_load_workspace_journal(artifact_key, artifact_class, context=None)` helper that:
  - Reads the workspace artifact at `artifact_key`
  - Returns `(data, error, input_context)` tuple
  - Handles missing-file / parse-error cases uniformly
- Migrate at minimum 10 representative `_load_or_read_workspace_*` call sites to use the helper.
- Remaining 22 functions are refactored in a follow-up or documented as pending.
- No behavior change to workspace artifact reading, error handling, or consumer APIs.
- Existing `test_artifact_tools.py` tests pass; add focused tests for the helper.

## Worker D acceptance criteria (Bare Except B-3)

- Add `import logging; _logger = logging.getLogger(__name__)` at module level (if not present).
- Each of the 11 bare `except Exception:` blocks gets `_logger.debug("...", exc_info=True)` with
  a descriptive message indicating what operation was attempted and what fallback value is used.
- The one pure `pass` at line 6561 additionally gets a `# noqa: intentional — <reason>` comment.
- No behavior change to error handling, return values, or control flow.
- Existing `test_page_mutation.py` tests pass.

## Validation gate (per-worker)

Before requesting merge, each worker must:
1. `git diff --check` — clean
2. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src/reverse_deepagent tests`
3. Targeted tests for the owned files pass locally
4. Diff is limited to the assigned write set

## Main-agent review checklist

For each worker PR:
1. Branch based on `refactor/consolidate-hooks-native-web`, PR targets that base
2. Diff matches assigned write set (no scope creep)
3. Worker validation commands present and passing
4. `git diff --check` passes after merge
5. Targeted tests pass on merged base

## Final rollout validation

After all PRs are merged:
```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src/reverse_deepagent tests
PATH=".venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

## Final results

| File | Before | After | Delta | Worker |
|---|---|---|---|---|
| `native_web.py` | 14,317 | 13,436 | **-881** | A (S2) |
| `native_web_source_dispatch.py` | 219 | 710 | +491 | A (S2) |
| `coordinator.py` | 2,212 | 1,974 | **-238** | B (B-1) |
| `runtime/mock_bridge.py` | — | 236 | +236 | B (B-1) |
| `runtime/browser_lifecycle.py` | — | 44 | +44 | B (B-1) |
| `artifact_tools.py` | 13,842 | 13,749 | **-93** | C (B-2) |
| `page_mutation.py` | 9,509 | 9,523 | +14 | D (B-3) |

### Per-worker status

| Worker | Branch | PR | Result |
|---|---|---|---|
| A | `rollout12-source-dispatch-s2` | Direct commit `93e0b6a9` | ✅ 10 branches extracted, 316 targeted tests pass |
| B | `rollout12-coordinator-b1-phase1` | Direct merge `05090444` | ✅ MockJSReverserBridge + Chrome lifecycle extracted, 12 tests pass |
| C | `rollout12-journal-loader-b2` | Direct merge `77028a8e` | ✅ 11/32 loader functions migrated to common helper, 189 tests pass |
| D | `rollout12-bare-except-b3` | Fast-forward merge `1a8fc942` | ✅ 11 bare excepts with debug logging, 73 tests pass |

### Final validation (2026-06-22)

```text
$ git diff --check  # clean
$ compileall -q src/reverse_deepagent tests  # all modules OK
$ python -m unittest discover -s tests -v
Ran 1765 tests in 69.075s
OK (skipped=2)
```

### Known issue

Concurrent agents shared the same working directory without worktree isolation,
causing commits to land on wrong branches. Untangled via cherry-pick. Future
rollouts should use `isolation: "worktree"` for parallel agents.

## Follow-up after rollout 12

- Source Dispatch S3-S7 (explicit application branches, ~24 remaining in `_dispatch_source`)
- Coordinator B-1 Phase 2 (factories + registry + manifest extraction, ~720 lines remain)
- Journal loader remaining 21 function migration (same pattern, mechanical)
- README convergence (B-6)
- Internal registry re-location (B-5 — not found in current codebase)
