# Code audit triage for rollout 8

Date: 2026-06-12

Worker: T

Base branch: `refactor/consolidate-hooks-native-web`

Working branch: `codex/rollout8-audit-triage`

Primary scope: re-check the readonly audit themes against the current HEAD and turn them into a tracked triage document. The old local-only report `docs/status/2026-06-12-readonly-code-audit.md` was intentionally not read from or committed in this worktree.

## Executive summary

| Area | Classification | Priority | Current conclusion |
| --- | --- | --- | --- |
| Sensitive evidence / artifact redaction | still-open + needs-implementation-rollout | P0 | Native storage and network collectors can still emit raw cookie / header values. Existing redaction helpers are fragmented and not reused by collectors. |
| `scripts/start_chrome_debug.sh` hardening | partially-addressed | P1 | This PR applies one narrow hardening for `EXTRA_CHROME_ARGS` splitting to avoid pathname expansion. Other parameter-boundary issues remain follow-up work. |
| README legacy runtime alias cleanup | partially-addressed; default-runtime concern is stale-superseded | P2 | Current README already states `legacy-mcp` is compatibility-only and `mcp` / `jsreverser-mcp` are deprecated aliases. Remaining cleanup is mostly long-tail docs / tests wording, not a default-runtime bug. |
| Oversized `_dispatch_source(...)` helper | still-open + needs-implementation-rollout | P1 | The helper is still a 3.8k-line dispatch body. It should be decomposed by explicit-review-only source-map / hook domains, not opportunistically mixed with behavior changes. |

## Evidence reviewed on current HEAD

- `src/reverse_deepagent/browser/collectors/storage.py`
- `src/reverse_deepagent/browser/collectors/network.py`
- `src/reverse_deepagent/browser/hooks/page_mutation.py`
- `src/reverse_deepagent/browser_provider_smoke.py`
- `src/reverse_deepagent/browser/source_maps.py`
- `scripts/start_chrome_debug.sh`
- `README.md`
- `docs/runtime/jsreverser-mcp-setup.md`
- `docs/runtime/browser-provider-architecture.md`
- `docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md`
- `src/reverse_deepagent/adapters/native_web.py`
- `tests/test_browser_collectors.py`
- `tests/test_coordinator.py`
- `tests/test_console_script.py`
- `tests/test_fixture_cli.py`
- `tests/test_run_demo_chrome_lifecycle.py`

## 1. Sensitive evidence / artifact redaction

Classification: **still-open + needs-implementation-rollout**

Priority: **P0**

### Current evidence

`StorageCollector` still evaluates and returns raw browser context:

- `document.cookie` is returned as `cookie`.
- `localStorage` and `sessionStorage` values are returned as full key/value maps.
- Error fallback also preserves the `cookie` output shape, so downstream callers expect this raw field to exist.

`NetworkCollector` still records headers directly from Playwright-like request / response objects:

- request `headers` are copied without filtering;
- response `response_headers` are copied without filtering;
- obvious sensitive header names such as `Authorization`, `Cookie`, `Set-Cookie`, `Proxy-Authorization`, `X-API-Key`, or bearer-token-like custom headers are not normalized before snapshot output.

Existing redaction mechanisms are real but local to other surfaces:

- `browser_provider_smoke.py` has URL / proxy / browser-arg redaction for BrowserProvider smoke metadata and command hints.
- `browser/source_maps.py` uses credentialless fetch metadata and URL redaction.
- `browser/hooks/page_mutation.py` contains `_SENSITIVE_RE` patterns for heap / object-root summaries, but those helpers redact candidate names and selected payload fields, not general collector evidence.
- Delivery providers have URL / token metadata redaction, but that is a delivery boundary and not a native collector contract.

The collector test fixture currently uses `cookie: sid=redacted`, which proves shape compatibility but does not prove redaction behavior. Network collector fixtures also use harmless headers and therefore do not guard against raw `Authorization` / `Cookie` leakage.

### Risk

This is the highest-risk audit item because native Web recon artifacts can be persisted under `workspace/`, `exports/`, and manifest indexes. Raw cookie strings, bearer tokens, proxy auth headers, CSRF tokens, and account-bound storage values can move from ephemeral browser context into durable artifacts and PR attachments. That conflicts with the project rule that collector / hook evidence must avoid leaking raw cookie values, `Authorization`, proxy passwords, request bodies containing tokens, or other credentials.

### Recommended implementation rollout

Create a focused redaction rollout rather than patching one collector at a time:

1. Add a small central redaction module for browser evidence, for example `reverse_deepagent.browser.redaction`, with:
   - sensitive key matcher derived from existing `_SENSITIVE_RE` coverage: `token`, `secret`, `password`, `passwd`, `cookie`, `authorization`, `apikey`, `api_key`, `credential`, `csrf`, `session`, `bearer`, `proxy-authorization`, and `set-cookie`;
   - `redact_mapping(...)` for case-insensitive header / storage maps;
   - `redact_cookie_header(...)` that preserves cookie names and count but replaces values;
   - `redact_header_value(...)` that preserves safe structural hints such as scheme (`Bearer <redacted>`) and blocks full values;
   - metadata fields such as `redacted: true`, `redacted_fields`, and `raw_value_available: false` where useful.
2. Update `StorageCollector` to emit redacted cookie and storage summaries by default. If future rebuild planning needs raw values for explicitly reviewed local-only contexts, that should be gated as a separate opt-in path with artifact metadata proving it was not exported.
3. Update `NetworkCollector` to redact request / response headers before `snapshot()` returns them. Keep original request method, URL, status, resource type, and non-sensitive header names.
4. Add tests with raw `Authorization`, `Cookie`, `Set-Cookie`, `Proxy-Authorization`, `X-API-Key`, `csrf_token`, `sessionStorage` nonce, and localStorage token examples. Assertions should verify the raw values are absent from `str(snapshot)`.
5. Audit coordinator artifact extraction and manifest writing to make sure redacted collector output stays redacted when serialized.

Suggested worker split:

- **Worker T1 / redaction core**: central browser redaction helpers and unit tests.
- **Worker T2 / collector rollout**: StorageCollector + NetworkCollector adoption and artifact-shape tests.
- **Worker T3 / pipeline guard**: coordinator / manifest / review-gate regression proving raw secrets do not reappear after serialization.

## 2. `scripts/start_chrome_debug.sh` hardening

Classification: **partially-addressed**

Priority: **P1**

### Current evidence

The launcher is intentionally parameterized through environment variables:

- `CHROME_PATH`
- `CHROME_APP_NAME`
- `DEBUG_PORT`
- `DEBUG_ADDRESS`
- `USER_DATA_DIR`
- `STATE_DIR`
- `START_URL`
- `WAIT_SECONDS`
- `EXTRA_CHROME_ARGS`
- `PID_FILE`
- `OWNERSHIP_FILE`

Before this branch, `EXTRA_CHROME_ARGS` was expanded through an unquoted array assignment. That split string values and also allowed pathname expansion. This PR changes the narrow parsing step to `read -r -a extra_args <<< "$EXTRA_CHROME_ARGS"`, preserving the existing whitespace-split contract while avoiding glob expansion.

### Remaining risk

The script still has parameter-boundary issues that are better handled in a dedicated rollout:

- `EXTRA_CHROME_ARGS` remains a string interface, not a lossless argv array. It still cannot represent arguments containing whitespace without a future explicit array / file / repeated-flag interface.
- `CHROME_PATH` is checked for executability, but launch still uses `open -na "$CHROME_APP_NAME"`. A mismatched `CHROME_PATH` / `CHROME_APP_NAME` can pass validation for one executable and launch another app by name.
- `DEBUG_PORT` and `WAIT_SECONDS` are not validated before use in `lsof` and arithmetic expansion.
- `DEBUG_ADDRESS` is passed through to Chrome but listener detection checks only the port.
- `USER_DATA_DIR`, `STATE_DIR`, `PID_FILE`, and `OWNERSHIP_FILE` are quoted, but there is no boundary guard against surprising relative paths, symlinked state paths, or ownership-file collisions.
- `START_URL` is intentionally flexible but unclassified. For local smoke this is normally `about:blank` or a fixture URL; future hardening can document that it is not a secret-safe field.

### Recommended implementation rollout

Keep this script small and avoid turning it into a cross-platform launcher framework:

1. Add validation for `DEBUG_PORT` as integer `1..65535` and `WAIT_SECONDS` as non-negative integer.
2. Decide whether macOS launch should be app-name authoritative or executable-path authoritative. If executable path is authoritative, replace `open -na "$CHROME_APP_NAME"` with a reviewed path-based launch strategy and update docs / tests.
3. Add a documented `EXTRA_CHROME_ARGS_FILE` or repeated CLI-level option upstream if quoted / whitespace-containing args are required. Do not emulate shell parsing with `eval`.
4. Add `bash -n scripts/start_chrome_debug.sh` plus a dry-run-ish shell test harness that verifies argument array construction without starting Chrome.

Suggested worker split:

- **Worker U1 / shell validation**: numeric validation and syntax tests.
- **Worker U2 / launch authority decision**: `CHROME_PATH` vs `CHROME_APP_NAME` contract and docs update.
- **Worker U3 / args interface**: optional safer extra-args file or upstream repeated argument support.

## 3. README legacy runtime alias cleanup

Classification: **partially-addressed**, with the earlier “MCP is still the default center” concern now **stale-superseded**

Priority: **P2**

### Current evidence

The current README already says the canonical architecture is `native-web + BrowserProvider`, while legacy MCP is a compatibility backend. The runtime registry section states:

- `legacy-mcp` is supplied by the optional `reverse-deepagent-legacy-mcp` package.
- `mcp` and `jsreverser-mcp` are old aliases only.
- CLI usage of those old aliases emits a deprecation warning.
- New scripts should use `legacy-mcp` instead of old aliases.
- Without the optional package, `legacy-mcp` / `mcp` construction returns structured install guidance rather than starting the core MCP stdio transport.

The legacy setup doc also says to use `--runtime legacy-mcp` for new commands, while retaining old aliases only for the compatibility window.

### Remaining cleanup

There are still many legitimate occurrences of `mcp` in docs and tests because MCP remains a compatibility backend and test coverage needs to assert deprecated alias behavior. The cleanup target should not be “delete every `mcp` string.” It should be narrower:

- command examples in active docs should prefer `--runtime legacy-mcp` unless specifically testing deprecated aliases;
- headings and prose should avoid implying that MCP is the BrowserProvider abstraction boundary;
- tests named around `mcp` can remain if they explicitly verify alias warning or legacy plugin behavior;
- old planning docs may keep historical wording but should not be treated as current instructions when README / runtime docs have newer status.

### Recommended implementation rollout

This is lower priority than redaction because the primary README stance is already correct.

1. Run a docs-only grep for `--runtime mcp`, `--runtime jsreverser-mcp`, `runtime=mcp`, and `runtime jsreverser-mcp` across current user-facing docs.
2. Update only active how-to docs and examples, not historical plan records unless they are clearly misleading as current instructions.
3. Keep tests that intentionally cover deprecation warnings, but add a comment where needed so future reviewers do not “cleanup” alias tests by accident.
4. Optionally add a lightweight doc lint in a later rollout that blocks new active-doc examples using deprecated aliases outside a whitelist.

Suggested worker split:

- **Worker V1 / active docs grep**: README + `docs/runtime/*` examples only.
- **Worker V2 / compatibility tests annotation**: clarify alias-warning tests without changing behavior.
- **Worker V3 / optional lint**: whitelist-based check for future docs.

## 4. Oversized `_dispatch_source(...)` helper

Classification: **still-open + needs-implementation-rollout**

Priority: **P1**

### Current evidence

`NativeWebRuntime._dispatch_source(...)` currently spans approximately lines `2740..6592` in `src/reverse_deepagent/adapters/native_web.py`, about `3853` lines by the current inclusive count. The rollout 8 status doc records the same concern as a 3.8k-line helper and assigns a separate Worker S decomposition plan.

This helper is not just “long”; it mixes many review-only source-map / hook / dispatch surfaces into one method. That makes it easy to accidentally change side-effect policy while moving branches. Many branches must keep invariants such as:

- `review_only=true`
- `plan_only=true`
- `browser_started=false`
- `runtime_evaluated=false`
- `cdp_command_sent=false`
- `hook_installed=false`
- `automatic_hook_installation=false`
- `calls_mcp=false`
- `mobile_runtime_used=false`

### Recommended implementation rollout

Do not decompose this helper opportunistically while fixing unrelated bugs. Treat it as an extraction program with narrow review gates:

1. Land / review Worker S’s decomposition plan first.
2. Extract pure request-classifier predicates into a source-dispatch module without changing return payloads.
3. Extract descriptor-to-`ProtectionResult` builders by domain: candidate selection, candidate refinement, follow-through approval, transaction preflight / journal, bounded executor gates, selected result checkpoints, terminal review / closure / final audit, and credentialless source-map fetch surfaces.
4. Add golden-shape tests for representative branches before moving branch bodies.
5. Keep each PR branch-count-limited. One PR should not move the whole helper.
6. Preserve explicit-review-only and no-side-effect flags in every extraction.

Suggested worker split:

- **Worker S1 / classifier extraction**: no payload changes, targeted tests.
- **Worker S2 / descriptor builder extraction**: one source-map subdomain at a time.
- **Worker S3 / transaction / journal review surfaces**: preserve approval and side-effect gates.
- **Worker S4 / final shrink pass**: remove dead local duplication after branches are extracted and tests are green.

## Priority order for next rollout

1. **P0 redaction rollout**: native collector evidence redaction is the only item here that can leak secrets into durable artifacts. Do this before broadening native collector usage.
2. **P1 source dispatch decomposition**: reduce `_dispatch_source(...)` risk after Worker S plan is available; avoid mixing with redaction changes.
3. **P1 Chrome launcher hardening**: continue from the small `EXTRA_CHROME_ARGS` hardening in this PR with validation and launch-contract tests.
4. **P2 legacy alias cleanup**: docs-only sweep after higher-risk code paths are stabilized.

## Status notes

- The readonly audit report remains local-only and untracked in the main worktree. It is not present in this worktree and was not staged.
- This branch intentionally does not touch Worker R’s fallback contract document, Worker S’s source dispatch plan document, `ROADMAP.md`, or rollout status docs.
- The only code change included here is the narrow `EXTRA_CHROME_ARGS` glob-expansion hardening in `scripts/start_chrome_debug.sh`; all other findings are triaged as follow-up implementation work.
