# Multi-agent rollout 11: post-rollout-10 follow-up execution

Date: 2026-06-13

Base branch: `refactor/consolidate-hooks-native-web`

Status: completed

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
| A | `codex/rollout11-chrome-launcher-hardening` | P1 Chrome launcher hardening | `scripts/start_chrome_debug.sh`, packaged Chrome scripts, `tests/test_chrome_launcher.py`, focused README launcher docs | Merged in [#45](https://github.com/Facetomyself/reverse-deepagent/pull/45) / `e5da9240` |
| B | `codex/rollout11-legacy-alias-docs` | P2 active-doc legacy alias cleanup | README / active runtime docs / alias-warning test comments only | Merged in [#46](https://github.com/Facetomyself/reverse-deepagent/pull/46) / `b3355119` |
| C | `codex/rollout11-source-dispatch-s1` | P1 `_dispatch_source(...)` S1 minimal decomposition | `native_web.py`, optional source-dispatch helper module, focused native-web / source-map tests | Merged in [#47](https://github.com/Facetomyself/reverse-deepagent/pull/47) / `5d0b70bf` |

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

## Worker A result

Worker A is complete and merged through PR [#45](https://github.com/Facetomyself/reverse-deepagent/pull/45).

Merge commit: `e5da9240fae9a22ddc09eed7612fd29c43fdac63`.

Main-agent review verified that the PR touched only the Chrome launcher write set:

- `README.md` launcher parameter documentation;
- root and packaged Chrome start / stop scripts;
- `tests/test_chrome_launcher.py`.

Validation reported before merge:

```bash
bash -n scripts/start_chrome_debug.sh scripts/stop_chrome_debug.sh src/reverse_deepagent/scripts/start_chrome_debug.sh src/reverse_deepagent/scripts/stop_chrome_debug.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_chrome_launcher tests.test_run_demo_chrome_lifecycle -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
git diff --check
```

Observed locally: all commands passed; no real Chrome launch was performed.

## Worker B acceptance criteria

- New user-facing examples do not recommend deprecated `--runtime mcp` or
  `--runtime jsreverser-mcp` values.
- Kept `mcp` / `jsreverser-mcp` mentions are explicitly legacy backend, optional
  package, compatibility alias, self-hosted smoke, package name, transport, or test
  coverage references.
- Runtime architecture wording continues to state that `native-web + BrowserProvider`
  is the Web mainline and `legacy-mcp` is compatibility only.
- Runtime behavior and alias-warning assertions are unchanged.

## Worker B result

Worker B is complete and merged through PR [#46](https://github.com/Facetomyself/reverse-deepagent/pull/46).

Merge commit: `b33551198156e4dceba3a28a3b08416eff6818d7`.

Main-agent review verified that the PR touched only active legacy alias docs and
compatibility-test comments:

- `docs/runtime/adapter-pluginization-contract.md`;
- `docs/runtime/web-runtime-assumptions.md`;
- `tests/test_console_script.py`;
- `tests/test_coordinator.py`.

Validation reported / rerun before merge:

```bash
git diff --check
rg -n -- '--runtime mcp|--runtime jsreverser-mcp|runtime=mcp|runtime jsreverser-mcp' README.md docs/runtime docs/ci tests
PATH="/Users/mengma/reverse/reverse_agent/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_coordinator tests.test_console_script -v
```

Observed locally: diff check passed; remaining grep hits are explicit deprecated
alias compatibility notes; 16 targeted tests passed.

## Worker C acceptance criteria

- The S1 extraction keeps `_dispatch_source(...)` predicate order semantics intact.
- Only low-side-effect read-only / review-only Source Map evidence branches are moved.
- Explicit application branches remain in place for later S2-S7 work.
- Result payloads keep artifact paths, metadata, status, next action, confidence, and
  side-effect policy semantics.
- No browser, CDP, MCP, mobile, workspace path, artifact schema, or backend manifest
  behavior is added.

## Worker C result

Worker C is complete and merged through PR [#47](https://github.com/Facetomyself/reverse-deepagent/pull/47).

Merge commit: `5d0b70bf27efd97cf530c22e3d56b42b25af9c88`.

Main-agent review verified that the PR touched only the Source Dispatch S1 write set:

- `src/reverse_deepagent/adapters/native_web.py`;
- `src/reverse_deepagent/adapters/native_web_source_dispatch.py`;
- `tests/test_native_web_runtime.py`.

Migrated predicates:

- `_is_source_map_lookup_request(...)`;
- `_is_source_map_source_content_request(...)`;
- `_is_bundler_symbol_scope_request(...)`.

Explicit application branches, fetch, rebuild, dispatcher result, debugger / hook /
source-logpoint application, and higher-risk Source Map follow-through branches remain
in `_dispatch_source(...)` for later S2-S7 work.

Validation reported / rerun before merge:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_native_web_runtime tests.test_source_maps -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
```

Observed locally: diff check passed; 316 targeted tests passed; compileall passed.

## Final rollout validation

Final validation is run on `refactor/consolidate-hooks-native-web` after PR #45,
PR #46, and PR #47 are merged.

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
PATH="/Users/mengma/reverse/reverse_agent/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
```

Final validation status: **passed (2026-06-22)**. Consolidated post-merge validation
on `refactor/consolidate-hooks-native-web` (HEAD `5d0b70bf`) produced:

```text
$ git diff --check
(no output — clean)

$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src/reverse_deepagent tests
(no output — all modules compile)

$ PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
Ran 1765 tests in 68.547s
OK (skipped=2)
```

All three validation gates pass. The rollout 11 `completed` status is
evidence-backed as of 2026-06-22. The placeholder identified in the 2026-06-15
progress review is now resolved.

## Follow-up priorities after rollout 11

1. Continue `_dispatch_source(...)` decomposition with S2 selected executor review /
   approval / preflight, keeping explicit application branches isolated.
2. Continue S3-S7 only as separate PRs with narrow write sets and focused result-shape
   tests.
3. Keep longer-term Source Map full binding / automatic follow-through, heap proof
   executors, third-party production BrowserProvider validation, and mobile / mini-program
   full runtime chains as demand-driven follow-up work.

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
