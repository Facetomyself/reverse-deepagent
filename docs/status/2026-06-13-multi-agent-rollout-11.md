# Multi-agent rollout 11: post-rollout-10 follow-up execution

Date: 2026-06-13

Base branch: `refactor/consolidate-hooks-native-web`

Status: dispatching

## Objective

Rollout 11 starts the next wave of planned-but-incomplete work after rollout 10
closed the default Native Web fallback helper extraction. The main agent keeps the
coordination, review, merge, and final validation responsibility; workers own bounded
implementation slices on separate branches and PRs.

The rollout intentionally avoids mixing unrelated risks in a single PR. Chrome
launcher hardening, active legacy-alias documentation cleanup, and `_dispatch_source(...)`
S1 decomposition have disjoint write sets and separate validation gates.

## Dispatch matrix

| Worker | Branch | Scope | Owned files / areas | PR status |
| --- | --- | --- | --- | --- |
| A | `codex/rollout11-chrome-launcher-hardening` | P1 Chrome launcher hardening | `scripts/start_chrome_debug.sh`, packaged Chrome scripts, `tests/test_chrome_launcher.py`, focused README launcher docs | Dispatched |
| B | `codex/rollout11-legacy-alias-docs` | P2 active-doc legacy alias cleanup | README / active runtime docs / alias-warning test comments only | Dispatched |
| C | `codex/rollout11-source-dispatch-s1` | P1 `_dispatch_source(...)` S1 minimal decomposition | `native_web.py`, optional source-dispatch helper module, focused native-web / source-map tests | Dispatched |

## Worker A acceptance criteria

- `DEBUG_PORT` is validated as an integer in range `1..65535` before use in `lsof`,
  Chrome args, PID files, or ownership files.
- `WAIT_SECONDS` is validated as a non-negative integer before arithmetic expansion.
- Root and packaged start scripts stay behaviorally aligned.
- Existing `EXTRA_CHROME_ARGS` whitespace-split contract is preserved and no `eval`
  or shell parser emulation is introduced.
- `CHROME_PATH` vs `CHROME_APP_NAME` authority is documented without turning the
  script into a broad launcher framework.
- Validation includes shell syntax checks and focused Chrome launcher lifecycle tests
  without starting real Chrome.

## Worker B acceptance criteria

- New user-facing examples do not recommend deprecated `--runtime mcp` or
  `--runtime jsreverser-mcp` values.
- Kept `mcp` / `jsreverser-mcp` mentions are explicitly legacy backend, optional
  package, compatibility alias, self-hosted smoke, package name, transport, or test
  coverage references.
- Runtime architecture wording continues to state that `native-web + BrowserProvider`
  is the Web mainline and `legacy-mcp` is compatibility only.
- Runtime behavior and alias-warning assertions are unchanged.

## Worker C acceptance criteria

- The S1 extraction keeps `_dispatch_source(...)` predicate order semantics intact.
- Only low-side-effect read-only / review-only Source Map evidence branches are moved.
- Explicit application branches remain in place for later S2-S7 work.
- Result payloads keep artifact paths, metadata, status, next action, confidence, and
  side-effect policy semantics.
- No browser, CDP, MCP, mobile, workspace path, artifact schema, or backend manifest
  behavior is added.

## Main-agent review and merge checklist

For each worker PR, the main agent must verify:

1. Branch is based on `refactor/consolidate-hooks-native-web` and PR targets that base.
2. Diff is limited to the assigned write set.
3. Worker validation commands are present and relevant.
4. `git diff --check` passes after merge.
5. Targeted tests for the touched area pass locally on the merged base.
6. No runtime artifacts, `.venv`, cache files, or `docs/status/2026-06-12-readonly-code-audit.md`
   are included.

Final rollout 11 closure additionally requires updating this file and `ROADMAP.md`
with the actually merged PRs and final validation results.
