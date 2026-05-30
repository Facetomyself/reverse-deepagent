# JSReverser MCP setup assumptions

This document describes the legacy JSReverser MCP wiring for local, authorized Web / JavaScript reverse-engineering workflows. MCP is retained as a compatibility backend while `native-web` and BrowserProvider-based instrumentation are built.

## Architecture boundary

`jsreverser-mcp` is treated as a **legacy runtime backend**, not as the agent architecture boundary. The target architecture is documented in [`browser-provider-architecture.md`](browser-provider-architecture.md).

Use `--runtime legacy-mcp` in new commands. The old `--runtime mcp` and `--runtime jsreverser-mcp` values still resolve to `legacy-mcp` during the compatibility window, but CLI entrypoints print a deprecation warning when those aliases are used.

```text
DeepAgents coordinator / subagents
  -> reverse_deepagent runtime adapter
    -> JSReverser MCP stdio process
      -> Chrome DevTools remote debugging endpoint
```

The upper layers should consume normalized runtime evidence and artifacts, not raw MCP tool names or raw MCP return shapes.

This is deliberate:

- MCP transports and tool names are allowed to change.
- JSReverser MCP often returns Markdown, fenced JSON, and trace IDs in one response.
- The agent should reason over stable schemas such as `ReconResult`, `EvidenceItem`, `runtime-context.json`, and `rebuild-plan.json`.

## Local prerequisites

For real MCP-backed smoke tests you need:

1. Python 3.11+.
2. An editable install of this package.
3. A local `jsreverser-mcp` executable.
4. A Chrome-compatible browser that can be launched with `--remote-debugging-port`.
5. A local target or fixture that you are authorized to analyze.

The default MCP command currently assumes Homebrew-style macOS install location:

```text
/opt/homebrew/bin/jsreverser-mcp
```

You can probe this manually:

```bash
command -v jsreverser-mcp || test -x /opt/homebrew/bin/jsreverser-mcp
```

If your binary lives elsewhere, pass the explicit command to scripts that expose a command option, or create a wrapper / symlink for local testing. The optional `reverse-deepagent-legacy-mcp` package now owns `JSReverserMcpConfig` and the stdio bridge; core CLI / workflow inputs pass through `reverse_deepagent.runtime.legacy_mcp` as a shim and return install guidance when the optional package is absent.

## Chrome remote debugging lifecycle

Do **not** assume port `9222` is already open.

Prefer the managed launcher:

```bash
reverse-agent-fixture-smoke \
  --profile context-navigator \
  --runtime legacy-mcp \
  --ensure-chrome \
  --jsreverser-mcp-command "/opt/homebrew/bin/jsreverser-mcp" \
  --chrome-debug-port 9461 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-9461"
```

The launcher is backed by:

- `scripts/start_chrome_debug.sh`
- `scripts/stop_chrome_debug.sh`

Important parameters:

| Parameter | Purpose |
| --- | --- |
| `--chrome-debug-port` | Remote debugging port passed to Chrome and the MCP backend. |
| `--chrome-debug-address` | Bind address, usually `127.0.0.1`. |
| `--chrome-user-data-dir` | Isolated Chrome profile directory. Use a temp profile for smoke tests. |
| `--chrome-path` | Chrome executable path. Defaults to the common macOS path. |
| `--chrome-extra-args` | Extra Chrome flags, passed through the launcher. |
| `--keep-chrome` | Keep managed Chrome running after the smoke. Default is to stop it. |
| `--jsreverser-mcp-command` | MCP executable path used by the runtime adapter. Keep this aligned with any CI `jsreverser_mcp_path` input. |

The runtime adapter must pass the same browser URL to JSReverser MCP:

```text
http://127.0.0.1:<chrome-debug-port>
```

If you customize the port but the MCP backend still connects to `9222`, the smoke is misconfigured.

## Recommended local smoke commands

### Probe MCP stdio

```bash
PYTHONPATH="src" \
python scripts/probe_jsreverser_mcp.py \
  --command "/opt/homebrew/bin/jsreverser-mcp" \
  --browser-url "http://127.0.0.1:9222"
```

The probe writes a summary to:

```text
artifacts/exports/jsreverser-mcp-probe.json
```

### Run fixture smoke with managed Chrome

```bash
reverse-agent-fixture-smoke \
  --profile context-cookie \
  --runtime legacy-mcp \
  --ensure-chrome \
  --jsreverser-mcp-command "/opt/homebrew/bin/jsreverser-mcp" \
  --chrome-debug-port 9460 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-9460" \
  --artifact-root "artifacts/fixture-context-cookie-mcp"
```

Try these profiles when checking context-aware rebuild behavior:

- `context-localstorage`
- `context-cookie`
- `context-navigator`
- `token-chain`
- `hybrid-context`

Try `webpack-minified` when checking bundled / minified Web source handling without extra runtime context.

Expected important artifacts:

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

## Public CI vs local MCP integration

The default GitHub Actions workflow does **not** run real MCP-backed browser tests.

Reasons:

- Hosted public runners do not have `jsreverser-mcp` installed.
- Hosted public runners may not provide the desktop Chrome setup expected by JSReverser MCP.
- Real browser automation can be flaky when mixed with generic hosted CI images.

Default public CI covers:

- Mock runtime pipeline.
- Fixture server behavior.
- Pure-Python rebuild generation.
- DeepAgents smoke tests with fake chat models.
- Runtime adapter normalization logic.

Real MCP smoke is isolated in the manual workflow:

```text
.github/workflows/mcp-integration.yml
```

Run it through GitHub Actions `workflow_dispatch` on a self-hosted runner that has Chrome and JSReverser MCP installed. For input-level operating instructions, see [`docs/ci/self-hosted-mcp-smoke.md`](../ci/self-hosted-mcp-smoke.md).

## Self-hosted runner checklist

Before running the manual `MCP Integration` workflow, verify:

```bash
python --version
command -v google-chrome || command -v chromium || test -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
test -x /opt/homebrew/bin/jsreverser-mcp
```

Recommended runner traits:

- Desktop-capable macOS or Linux runner.
- Chrome installed and executable by the runner user.
- `jsreverser-mcp` installed and executable by the runner user.
- Enough permissions to create temporary Chrome user-data directories.
- No long-running Chrome debug process already occupying the selected port.

## Troubleshooting

### `jsreverser-mcp` is missing

Symptom:

```text
No such file or directory: /opt/homebrew/bin/jsreverser-mcp
```

Fix:

- Install JSReverser MCP locally.
- Or pass the correct binary path where the command supports it.
- Or skip MCP integration and use `--runtime native-web` or `--runtime mock` for public demo verification.

### Chrome debug port is not reachable

Symptoms:

```text
BROWSER_DISCONNECTED
NO_ACTIVE_PAGE
Failed to connect and auto-launch browser
```

Fix:

- Use `--ensure-chrome`.
- Pick a free `--chrome-debug-port`.
- Use an isolated `--chrome-user-data-dir`.
- Check whether a previous Chrome process is still holding the port.

### MCP output is Markdown instead of plain JSON

This is expected. The adapter normalizes mixed return shapes including:

- Markdown headings.
- fenced JSON blocks.
- trace IDs.
- plain text request/source lists.

If a new MCP output shape appears, normalize it inside the runtime adapter instead of leaking raw MCP response parsing into the agent layer.

### Context-aware rebuild is not generated

Check:

- `workspace/runtime-context.json`
- `workspace/runtime-context-diff.json`
- `workspace/rebuild-plan.json`

Common causes:

- Source context did not expose a supported strategy marker.
- Required runtime context was detected but not captured.
- The algorithm depends on volatile values that are not safe to freeze into `sign_rebuild.py`.

## Boundary reminders

- Use local fixtures or authorized targets.
- Do not commit generated artifacts containing real cookies, tokens, or proprietary target code.
- MCP is a backend detail; keep durable outputs in normalized workspace artifacts.
