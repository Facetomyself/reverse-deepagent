# Multi-agent rollout 8: fallback contract, source dispatch planning, and audit triage

## Purpose

Continue the unfinished-work multi-agent program after rollout 7 completed B3c
direct request branch extraction. Rollout 8 moves from branch-moving work into
three bounded follow-ups:

1. Review a dedicated final fallback hook dispatch contract before any fallback
   hook code is moved out of `apply_minimal_protection(...)`.
2. Plan the next large decomposition around `_dispatch_source(...)`, which is
   now the largest native Web runtime helper.
3. Turn the readonly security / quality audit input into a current, tracked
   triage plan without accidentally committing the stale untracked audit report.

This rollout is expected to produce review / plan / triage documents first. It
must not change runtime behavior unless a worker explicitly owns a small audited
hardening patch with tests and the main agent verifies it.

## Baseline

Latest local baseline before rollout 8:

- Branch: `refactor/consolidate-hooks-native-web`.
- Local / upstream divergence: `0 0`.
- Open PRs: none.
- Untracked local file intentionally excluded from automatic staging:
  `docs/status/2026-06-12-readonly-code-audit.md`.
- `apply_minimal_protection`: lines 531-615, 85 lines.
- Direct request branch predicates in `apply_minimal_protection`: 0.
- Final fallback hook install / snapshot remains in `apply_minimal_protection`.
- `_dispatch_source`: lines 2740-6591, 3852 lines.

## Worker assignments

### Worker R: fallback hook dispatch contract

Branch:

```text
codex/rollout8-fallback-contract
```

Primary output:

```text
docs/runtime/native-web-fallback-dispatch-contract.md
```

Task:

- Design the contract for a future extraction of final fallback hook install /
  snapshot behavior from `apply_minimal_protection(...)`.
- Document invariants, call ordering, side-effect boundaries, evidence / artifact
  compatibility, rollback conditions, and test requirements.
- Do not move code in this rollout.

Do not touch:

- `src/reverse_deepagent/adapters/native_web.py`.
- `_dispatch_source(...)`.
- The readonly audit report.
- Runtime behavior, artifact schemas, workspace contract, BrowserProvider, MCP,
  Android, iOS, or mini-program paths.

### Worker S: `_dispatch_source(...)` decomposition plan

Branch:

```text
codex/rollout8-source-dispatch-plan
```

Primary output:

```text
docs/plans/2026-06-12-source-dispatch-decomposition-plan.md
```

Task:

- Analyze `_dispatch_source(...)` and propose a staged decomposition plan with
  helper boundaries, merge order, validation commands, and side-effect guards.
- The plan should preserve existing Source Map explicit-review-only boundaries
  and not turn review descriptors into automatic executors.
- Do not move code in this rollout.

Do not touch:

- `src/reverse_deepagent/adapters/native_web.py`.
- Fallback hook contract doc.
- The readonly audit report.
- Runtime behavior or artifact schemas.

### Worker T: audit triage plan

Branch:

```text
codex/rollout8-audit-triage
```

Primary output:

```text
docs/status/2026-06-12-code-audit-triage.md
```

Task:

- Re-check the current HEAD against the audit themes previously surfaced by the
  untracked readonly report.
- Produce a tracked triage document that classifies each item as still-open,
  already-fixed, stale / superseded, or needs focused implementation rollout.
- Prioritize sensitive evidence redaction, `scripts/start_chrome_debug.sh`
  argument hardening, README legacy runtime alias cleanup, and oversized helper
  decomposition.
- Do not commit `docs/status/2026-06-12-readonly-code-audit.md` unless the main
  agent later explicitly decides to archive it.

Optional code hardening:

- Worker T may implement a very small, directly related hardening patch only if
  it is low-risk, has focused tests or shell validation, and stays in a disjoint
  write set. Otherwise leave fixes as planned follow-ups.

Do not touch:

- Fallback hook contract doc.
- Source dispatch decomposition plan.
- Runtime behavior unless explicitly covered by the optional narrow hardening
  clause above.

## Merge order

1. Merge Worker R first if it is docs-only and clean.
2. Merge Worker S second if docs-only and clean.
3. Merge Worker T last because it may reference the other two documents and may
   include optional hardening.
4. Run focused validation after any code-changing PR.
5. Run final repository validation before closing the rollout.
6. Update this document and `ROADMAP.md` with final status.

## Validation commands

Docs-only worker validation:

```bash
git diff --check
```

Code-changing worker validation, if any:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
```

Final rollout validation:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
```

## Completion definition

This rollout is complete only when:

- Worker PRs for fallback contract, source dispatch plan, and audit triage are
  merged or explicitly superseded by the main agent with documented evidence.
- The readonly audit report remains untracked unless intentionally archived.
- No runtime behavior changes are made without tests and main-agent validation.
- `ROADMAP.md` and this status document reflect the final state.
- Open PR list is clean after merges.

## Current status

Status: completed for rollout 8.

## Execution result

Merged PRs:

| Worker | PR | Branch | Scope | Merge commit | Notes |
| --- | ---: | --- | --- | --- | --- |
| R | #38 | `codex/rollout8-fallback-contract` | Added `docs/runtime/native-web-fallback-dispatch-contract.md` describing the future default fallback helper contract | `83e65698` | Docs-only; main agent verified single-file scope and whitespace before merge. |
| S | #39 | `codex/rollout8-source-dispatch-plan` | Added `docs/plans/2026-06-12-source-dispatch-decomposition-plan.md` with staged `_dispatch_source(...)` decomposition plan | `163ad101` | Docs-only; main agent verified single-file scope and whitespace before merge. |
| T | #40 | `codex/rollout8-audit-triage` | Added tracked audit triage and applied narrow `EXTRA_CHROME_ARGS` glob-expansion hardening in `scripts/start_chrome_debug.sh` | `dbf7b777` | Main agent verified diff scope, `git diff --check`, and `bash -n scripts/start_chrome_debug.sh` before merge. |

Validation during PR review:

```text
# PR #38
git diff --check origin/refactor/consolidate-hooks-native-web...HEAD

# PR #39
git diff --check HEAD^ HEAD

# PR #40
git diff --check HEAD^ HEAD
bash -n scripts/start_chrome_debug.sh
```

Runtime / side-effect boundary:

- No Python runtime code changed in rollout 8.
- No artifact schema names changed.
- No workspace path or workspace contract changed.
- No BrowserProvider, CDP, MCP, Android, iOS, or mini-program behavior changed.
- `scripts/start_chrome_debug.sh` keeps the existing whitespace-split `EXTRA_CHROME_ARGS` contract but avoids unquoted glob expansion.
- `docs/status/2026-06-12-readonly-code-audit.md` remains intentionally untracked and was not staged.

## Follow-up priorities after rollout 8

1. **P0 native collector redaction rollout**: add central browser-evidence redaction helpers and apply them to `StorageCollector` / `NetworkCollector`, then prove raw cookie / Authorization / storage-token values do not appear in serialized snapshots or downstream artifacts.
2. **P1 fallback helper code extraction**: implement the default fallback helper only after the new contract, preserving no-match behavior and install-failure behavior.
3. **P1 `_dispatch_source(...)` staged decomposition**: begin with the safest plan batch and preserve review-only / explicit-review-only Source Map boundaries.
4. **P1 Chrome launcher hardening continuation**: validate numeric ports / waits and decide whether `CHROME_PATH` or `CHROME_APP_NAME` is authoritative.
5. **P2 README / active-doc legacy alias cleanup**: keep deprecated `mcp` / `jsreverser-mcp` examples only where explicitly testing compatibility.
