# BrowserProvider smoke policy gate

This document describes the side-effect-free BrowserProvider smoke policy gate used by public CI and PR review.

The gate lives in the default workflow:

```text
.github/workflows/ci.yml
```

It uses the console script:

```bash
reverse-agent-browser-provider-smoke-policy \
  --smoke-json "<path-to-workspace/browser-provider-smoke.json>" \
  --expected-provider cloakbrowser \
  --minimum-evidence-level launch-smoke
```

The script reads an existing UTF-8 JSON object and delegates to the same acceptance / policy logic used by `reverse-agent-browser-provider-smoke --review-smoke-json`. It outputs `reverse-deepagent.browser-provider-smoke-policy-gate.v1` and exits with:

- `0` when the policy passes.
- `2` when the policy blocks.

The gate output contains nested review objects that are part of the public smoke-evidence contract:

- `attachment_acceptance`: `reverse-deepagent.browser-provider-smoke-acceptance.v1`, the side-effect-free acceptance gate for already generated smoke evidence.
- `attachment_acceptance.acceptance_report`: `reverse-deepagent.browser-provider-smoke-acceptance-report.v1`, the reviewer-facing evidence summary and blocker / warning report.
- `policy_decision`: `reverse-deepagent.browser-provider-smoke-policy-decision.v1`, the minimum-evidence-level gate decision consumed by CI / PR checks.

## Public CI behavior

Public hosted CI does **not** start Playwright, CloakBrowser, Remote CDP, Browserless, Browserbase, legacy MCP, or mobile runtimes. The CI step reads fixed repository fixture evidence samples and verifies policy behavior:

| Fixture | Expected policy result | Purpose |
| --- | --- | --- |
| `tests/fixtures/browser-provider-smoke/cloakbrowser-metadata-only.json` | blocked with `insufficient_browser_provider_smoke_evidence_level` when `launch-smoke` is required | Proves metadata-only configuration evidence cannot satisfy runtime launch smoke. |
| `tests/fixtures/browser-provider-smoke/cloakbrowser-launch-smoke.json` | pass | Proves accepted launch-smoke evidence satisfies the CI / PR gate without launching a browser during CI. |

This proves the CI / PR gate contract without requiring a real browser session. The fixtures are synthetic, redacted, and side-effect explicit; they are not proof that a real CloakBrowser session ran on the hosted CI runner.

## Side-effect boundary

The policy gate must remain metadata-only and review-only. It must not:

- generate smoke evidence,
- resolve BrowserProvider registrations,
- invoke provider factories,
- check provider availability,
- launch browsers,
- probe CDP endpoints,
- write workspace artifacts,
- call MCP,
- touch Android / iOS / mini-program full runtime chains.

`metadata-only` evidence may be useful provider configuration evidence, but it must not be accepted as runtime launch smoke. Requiring `--minimum-evidence-level launch-smoke` blocks metadata-only or availability-check evidence with `insufficient_browser_provider_smoke_evidence_level`.

## Local usage

Run the gate against the built-in metadata-only fixture:

```bash
PYTHONPATH="src" \
".venv/bin/python" -m reverse_deepagent.browser_provider_smoke_policy \
  --smoke-json "tests/fixtures/browser-provider-smoke/cloakbrowser-metadata-only.json" \
  --expected-provider cloakbrowser \
  --minimum-evidence-level launch-smoke
```

This command should exit `2`. Run the pass fixture:

```bash
PYTHONPATH="src" \
".venv/bin/python" -m reverse_deepagent.browser_provider_smoke_policy \
  --smoke-json "tests/fixtures/browser-provider-smoke/cloakbrowser-launch-smoke.json" \
  --expected-provider cloakbrowser \
  --minimum-evidence-level launch-smoke
```

This command should exit `0`. Run the gate against an existing real smoke artifact:

```bash
PYTHONPATH="src" \
".venv/bin/python" -m reverse_deepagent.browser_provider_smoke_policy \
  --smoke-json "artifacts/browser-provider-smoke/workspace/browser-provider-smoke.json" \
  --expected-provider cloakbrowser \
  --minimum-evidence-level launch-smoke
```

After installing the package, the console script is equivalent:

```bash
reverse-agent-browser-provider-smoke-policy \
  --smoke-json "artifacts/browser-provider-smoke/workspace/browser-provider-smoke.json" \
  --expected-provider cloakbrowser \
  --minimum-evidence-level launch-smoke
```

Use `--block-on-warnings` when PR policy wants warnings to fail the gate instead of passing with `decision=warn`.
