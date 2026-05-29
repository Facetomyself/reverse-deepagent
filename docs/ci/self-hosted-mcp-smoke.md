# Self-hosted MCP smoke workflow

This document describes how to run and maintain the self-hosted GitHub Actions workflow for legacy JSReverser MCP + Chrome smoke coverage. The workflow supports both manual dispatch and a weekly scheduled canary on a self-hosted runner. MCP coverage is kept for compatibility while native BrowserProvider runtime coverage is developed.

The workflow lives at:

```text
.github/workflows/mcp-integration.yml
```

It is intentionally **not** part of the default public CI path. Public hosted runners do not provide the local `jsreverser-mcp` binary or a stable desktop Chrome debugging environment, so the default `CI` workflow stays mock / pure-Python only.

## What the workflow verifies

The `MCP Integration` workflow runs `reverse-agent-fixture-smoke` against the bundled localhost sign fixture with:

- real `runtime=legacy-mcp`
- managed Chrome remote-debugging lifecycle via `--ensure-chrome`
- a selected fixture profile or a named `profile_set` batch
- a temporary Chrome user-data directory under `$RUNNER_TEMP`
- a temporary artifact root under `$RUNNER_TEMP`
- artifact upload for generated smoke output and JSON summaries
- `$GITHUB_STEP_SUMMARY` entries for preflight and per-profile results

A successful run verifies that the runner can:

1. start or reuse the configured Chrome executable through the project launcher,
2. expose a reachable Chrome DevTools endpoint,
3. launch `jsreverser-mcp`,
4. collect Web runtime evidence through the MCP adapter,
5. produce normalized workspace / rebuild artifacts.

## Required runner traits

Use a self-hosted runner with these traits:

- Python 3.11 available to `actions/setup-python`.
- Chrome or Chromium installed and executable by the runner user.
- `jsreverser-mcp` installed and executable by the runner user.
- Permission to create temporary directories under `$RUNNER_TEMP`.
- Permission to launch a desktop browser process.
- No always-on Chrome debug process occupying the selected port.

Recommended local preflight on the runner host:

```bash
python3 --version
command -v google-chrome || command -v chromium || test -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
test -x /opt/homebrew/bin/jsreverser-mcp
```

If the MCP binary is not at `/opt/homebrew/bin/jsreverser-mcp`, pass the correct path through the workflow input `jsreverser_mcp_path`. The workflow forwards this value to `reverse-agent-fixture-smoke --jsreverser-mcp-command`, so the verified binary and the runtime binary stay the same.

## Workflow inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `runner_label` | `self-hosted` | GitHub Actions runner label. Use a more specific label if you have multiple self-hosted runners. |
| `profile` | `context-navigator` | Fixture profile used when `profile_set=selected`. |
| `profile_set` | `selected` manually, `core` on schedule | Profile batch to run: `selected`, `core`, `context`, `realistic`, or `all`. |
| `chrome_debug_port` | `9461` | Base Chrome remote debugging port; batch runs increment this port per profile. |
| `chrome_path` | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` | Absolute path to the Chrome executable on the runner. |
| `jsreverser_mcp_path` | `/opt/homebrew/bin/jsreverser-mcp` | Absolute path to the MCP executable on the runner. |

Supported profiles should match the fixture server profiles:

- `default`
- `md5`
- `sha1`
- `sha256`
- `base64`
- `context-localstorage`
- `context-cookie`
- `context-navigator`
- `webpack-minified`
- `token-chain`
- `hybrid-context`

Profile sets:

- `selected`: run only the `profile` input.
- `core`: run `default`, `sha256`, `base64`, and `context-navigator`. This is the scheduled default.
- `context`: run context-heavy profiles: `context-localstorage`, `context-cookie`, `context-navigator`, `token-chain`, and `hybrid-context`.
- `realistic`: run `webpack-minified`, `token-chain`, and `hybrid-context`.
- `all`: run every fixture profile.

## How to run from GitHub UI

1. Open the repository Actions tab.
2. Select `MCP Integration`.
3. Click `Run workflow`.
4. Choose a self-hosted runner label, fixture profile, and `profile_set`.
5. Pick a free `chrome_debug_port`; profile-set runs increment the port from this base.
6. Set `chrome_path` and `jsreverser_mcp_path` if the runner does not use the documented defaults.
7. Start the workflow and inspect the step summary plus uploaded artifacts.

## How to run with GitHub CLI

```bash
gh workflow run "MCP Integration" \
  --repo "Facetomyself/reverse-deepagent" \
  -f runner_label="self-hosted" \
  -f profile="context-navigator" \
  -f profile_set="selected" \
  -f chrome_debug_port="9461" \
  -f chrome_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  -f jsreverser_mcp_path="/opt/homebrew/bin/jsreverser-mcp"
```

Then watch the latest run:

```bash
gh run list --repo "Facetomyself/reverse-deepagent" --workflow "MCP Integration" --limit 3
gh run watch <run-id> --repo "Facetomyself/reverse-deepagent" --exit-status
```

## Expected outputs

The workflow writes smoke artifacts under:

```text
$RUNNER_TEMP/reverse-agent-mcp/<profile>
$RUNNER_TEMP/reverse-agent-mcp/<profile>-smoke.json
```

The `Upload MCP smoke artifacts` step uploads these paths as `reverse-agent-mcp-smoke-<run-id>` even when a later profile fails.

Important files include:

```text
workspace/runtime-context.json
workspace/runtime-context-diff.json
workspace/function-candidates.json
workspace/function-validations.json
workspace/function-validation-summary.json
workspace/rebuild-plan.json
rebuild/sign_rebuild.py
rebuild/replay_demo.py
rebuild/scrapy_middleware.py
```

For context-aware profiles, inspect `workspace/runtime-context-diff.json` to check whether collected context keys are stable or volatile across samples.

## Failure triage

### MCP binary check fails

Symptom:

```text
test -x "<path>" failed
```

Fix:

- install `jsreverser-mcp` on the runner,
- make it executable by the runner user,
- or pass the correct `jsreverser_mcp_path` input.

### Chrome debug port is unavailable

Symptoms:

```text
Failed to connect
BROWSER_DISCONNECTED
NO_ACTIVE_PAGE
```

Fix:

- choose a different `chrome_debug_port`,
- clean up stale Chrome processes on the runner,
- use an isolated Chrome user-data directory,
- verify the runner user can launch Chrome in its execution environment.

### Context-aware rebuild is partial

Check:

- whether the chosen profile actually requires runtime context,
- `workspace/runtime-context.json` for captured requirements,
- `workspace/runtime-context-diff.json` for volatile keys,
- `workspace/rebuild-plan.json` for `manual_port_required` and `context_aware_extractable`.

Volatile keys are not safe to freeze into generated pure-Python replay code without an explicit runtime binding decision.

## Maintenance notes

- Keep the workflow profile options and profile-set shell arrays in sync with `FIXTURE_PROFILE_VALUES` in `src/reverse_deepagent/fixtures/web_sign.py`.
- Do not upload generated artifacts from real third-party targets unless they are sanitized.
- Keep MCP-specific assumptions inside runtime docs and adapter code; do not leak raw MCP response parsing into the DeepAgents coordinator.
