# reverse-deepagent-strategy-detector-reference

Reference StrategyDetector plugin package for `reverse-deepagent`.

This package is intentionally small but real: it exposes a loadable
`StrategyDetectorProviderRegistration` through the
`reverse_deepagent.strategy_detectors` entry-point group and implements a pure
Python detector for deterministic marker inventory. It is meant to be a safe
fixture/reference provider for third-party StrategyDetector packages beyond the
copy-and-replace template.

## Entry point

```toml
[project.entry-points."reverse_deepagent.strategy_detectors"]
reference-strategy-detector = "reverse_deepagent_strategy_detector_reference:strategy_detector_registration"
```

## Side-effect policy

Registration and metadata listing are metadata-only. They may import this module
and construct the registration object, but they must not run the detector, read
external files, access the network, start a browser, evaluate JavaScript, call
MCP, install hooks, execute replay, or mutate files.

The detector itself is also pure and deterministic. It only inspects the
provided source string for conservative markers such as signing names, bearer /
nonce wording, HMAC / AES / RSA crypto markers, webpack bundling markers, and
fetch / XHR request markers. It does not collect runtime context and does not
interact with any BrowserProvider. Detector results expose redacted marker
metadata such as match spans and pattern digests; they do not serialize raw
source snippets or surrounding source context.

## Non-goals

- It does not prove a portable signing implementation.
- It does not extract live secrets, cookies, headers, profile data, or runtime
  state.
- It does not execute JavaScript or replay network requests.
- It does not replace site-specific detector packages; it provides a stable
  reference baseline and test fixture for the plugin contract.
