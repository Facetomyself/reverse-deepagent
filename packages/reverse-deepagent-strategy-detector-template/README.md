# reverse-deepagent-strategy-detector-template

Template StrategyDetector plugin package for `reverse-deepagent`.

This package shows the minimum shape for moving strategy detectors out of core
without changing the coordinator, BrowserProvider layer, or MCP compatibility
surface. Copy it when a detector corpus grows too large or when a site / vendor
specific signing detector should live in a private package.

## Entry point

The package exposes one registration through the
`reverse_deepagent.strategy_detectors` Python entry-point group:

```toml
[project.entry-points."reverse_deepagent.strategy_detectors"]
template-strategy-detector = "reverse_deepagent_strategy_detector_template:strategy_detector_registration"
```

`strategy_detector_registration()` returns a
`StrategyDetectorProviderRegistration` with serializable, non-secret metadata,
rule descriptions, and a detector callable. Loading metadata must not run the
detector, collect runtime context, launch browsers, evaluate JavaScript, call
MCP, execute replay, or mutate files.

## Replace these pieces

- Change `TEMPLATE_STRATEGY_DETECTOR_PROVIDER_ID` and aliases.
- Replace `template_detector()` with real conservative source-pattern logic.
- Replace `TEMPLATE_RULES` with the emitted strategy ids and descriptions.
- Keep metadata free of API keys, cookies, Authorization headers, proxy
  credentials, raw request headers, or other secrets.
- Keep detection pure and side-effect-free. Runtime-assisted evidence should be
  requested as review-only follow-up artifacts instead of collected from inside
  detector metadata listing.

The default template only detects the marker `TEMPLATE_SIGN_STRATEGY` and is
intended as copy-and-replace scaffolding.
