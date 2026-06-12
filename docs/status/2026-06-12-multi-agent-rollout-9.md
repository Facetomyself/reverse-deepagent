# Multi-agent rollout 9: native collector redaction

Date: 2026-06-12

Base branch: `refactor/consolidate-hooks-native-web`

Status: planned / dispatching

## Objective

Rollout 9 closes the P0 audit item from
`docs/status/2026-06-12-code-audit-triage.md`: native Web collector evidence must not
persist raw cookies, bearer tokens, proxy credentials, CSRF values, API keys, session
identifiers, or similarly sensitive storage / header values into durable snapshots,
workspace artifacts, fixture output, or manifest-indexed JSON.

This rollout is intentionally narrow. It must not change BrowserProvider lifecycle,
launch browsers, call CDP directly, call MCP, move workspace paths, change artifact
schema names, or broaden Android / iOS / mini-program runtime behavior.

## Current baseline evidence

- `src/reverse_deepagent/browser/collectors/storage.py` still evaluates and returns
  `document.cookie`, `localStorage`, and `sessionStorage` values directly.
- `src/reverse_deepagent/browser/collectors/network.py` still records request
  `headers` and response `response_headers` directly from Playwright-like request /
  response objects.
- No central `reverse_deepagent.browser.redaction` module exists yet.
- Existing tests prove collector shape, but they do not prove raw secret values are
  absent from stringified snapshots or downstream serialized artifacts.

## Worker split

### Worker U: redaction core

Branch: `codex/rollout9-redaction-core`

Owned files:

- `src/reverse_deepagent/browser/redaction.py`
- `tests/test_browser_redaction.py`

Responsibilities:

1. Add central browser-evidence redaction helpers.
2. Provide a case-insensitive sensitive-key matcher covering at least:
   `token`, `secret`, `password`, `passwd`, `cookie`, `authorization`,
   `proxy-authorization`, `set-cookie`, `apikey`, `api_key`, `credential`,
   `csrf`, `session`, and `bearer`.
3. Provide focused helpers for header values, cookie headers, and mapping values.
4. Preserve useful structural hints, such as header / cookie names and bearer scheme,
   while removing raw values.
5. Add unit tests that assert raw fixture values are absent from `str(result)`.

Out of scope:

- Do not edit collectors in this PR unless required for import smoke.
- Do not change coordinator or artifact manifests.

### Worker V: collector adoption

Branch: `codex/rollout9-collector-redaction`

Owned files:

- `src/reverse_deepagent/browser/collectors/storage.py`
- `src/reverse_deepagent/browser/collectors/network.py`
- `tests/test_browser_collectors.py`

Responsibilities:

1. Adopt `reverse_deepagent.browser.redaction` helpers after Worker U lands or by
   rebasing on Worker U.
2. Redact `document.cookie` output while preserving the existing `cookie` field.
3. Redact sensitive `localStorage` / `sessionStorage` values by key while preserving
   non-sensitive values and the existing object shape.
4. Redact request `headers` and response `response_headers` while preserving method,
   URL, status, resource type, request id, and header names.
5. Add collector tests with raw `Authorization`, `Cookie`, `Set-Cookie`,
   `Proxy-Authorization`, `X-API-Key`, `csrf_token`, `auth_token`, and session values;
   assert raw values are absent from stringified snapshots.

Out of scope:

- Do not modify coordinator serialization in this PR.
- Do not change collector artifact keys or workspace paths.

### Worker W: pipeline serialization guard

Branch: `codex/rollout9-redaction-pipeline-guard`

Owned files:

- `tests/test_coordinator.py`
- `tests/test_fixture_cli.py`
- Optional narrow test helpers / fixtures only if needed.

Responsibilities:

1. Add downstream regression coverage proving collector-redacted values remain redacted
   after coordinator / pipeline serialization and fixture CLI artifact emission.
2. Use fixture raw values such as `Bearer super-secret-token`,
   `sid=raw-session; csrf=raw-csrf`, `auth_token=raw-token`, and
   `csrf_token=raw-csrf`.
3. Assert those raw strings are absent from serialized JSON / result object string.
4. Keep tests side-effect-free: no browser launch, no real network, no MCP.

Out of scope:

- Do not introduce a new artifact schema or workspace path.
- Do not broaden runtime execution; this worker is test / guard focused.

## Merge order

1. Merge Worker U first because it introduces the shared helper API.
2. Rebase / update Worker V on Worker U, then merge collector adoption.
3. Rebase / update Worker W on Worker V, then merge downstream serialization guards.
4. Run focused validation after every code-changing merge.
5. Run final full validation, update this status document and `ROADMAP.md`, then push.

## Validation commands

Focused validation after Worker U:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_browser_redaction -v
```

Focused validation after Worker V:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_browser_redaction tests.test_browser_collectors -v
```

Focused validation after Worker W:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_browser_redaction tests.test_browser_collectors tests.test_coordinator tests.test_fixture_cli -v
```

Final rollout validation:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
```

## Completion definition

This rollout is complete only when:

- A central browser redaction helper exists and is covered by unit tests.
- Storage and network collectors use the helper by default.
- Raw cookie / Authorization / proxy auth / API key / CSRF / session / token fixture
  values are absent from collector snapshots and downstream serialized artifacts.
- Existing collector output shape remains compatible unless a separately reviewed
  migration is documented.
- No workspace paths, artifact schema names, BrowserProvider lifecycle behavior, CDP,
  MCP, Android, iOS, or mini-program runtime behavior are changed.
- Worker PRs are merged, final validation passes, and `ROADMAP.md` plus this status
  document reflect the final state.
