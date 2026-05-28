# Contributing

Reverse DeepAgent is currently maintained as a research/demo project for Web / JS reverse-engineering workflows.

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Runtime artifacts

Do not commit generated runtime artifacts. The following paths are intentionally ignored:

- `artifacts/`
- `artifacts-*/`
- `.venv/`
- `*.egg-info/`

## Chrome debug lifecycle

When testing MCP-backed Web recon, first read [`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md). For self-hosted GitHub Actions smoke runs, also read [`docs/ci/self-hosted-mcp-smoke.md`](docs/ci/self-hosted-mcp-smoke.md). Prefer the managed launcher instead of assuming port `9222` is already open:

```bash
reverse-agent-fixture-smoke \
  --profile context-navigator \
  --runtime mcp \
  --ensure-chrome \
  --chrome-debug-port 9461 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-9461"
```
