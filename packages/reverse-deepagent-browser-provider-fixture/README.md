# reverse-deepagent-browser-provider-fixture

Functional BrowserProvider plugin package for `reverse-deepagent` tests, CI, and
third-party integration examples.

Unlike `reverse-deepagent-browser-provider-template`, this package is not a
copy-only scaffold: its provider can actually `start()` and `connect()` to a
provider-neutral in-memory browser session. It does not launch a real browser,
probe CDP, import Playwright, call MCP, or provide stealth/fingerprint behavior.
Its purpose is to prove the external BrowserProvider entry-point path end to
end without adding heavyweight runtime dependencies.

## Entry point

```toml
[project.entry-points."reverse_deepagent.browser_providers"]
fixture-browser = "reverse_deepagent_browser_provider_fixture:browser_provider_registration"
```

`browser_provider_registration()` returns serializable non-secret capabilities
and a delayed factory. Registry metadata listing and doctor matrix paths must not
invoke the factory. The factory is called only when a caller explicitly creates
`fixture-browser` / `fixture` / `ci-browser-fixture`.

The capabilities also include `production_readiness` metadata with
`readiness_tier=fixture-only`. BrowserProvider matrix output should therefore
classify the fixture as `review-required`: it is useful for CI contract smoke,
but it is not a production browser runtime.

## Runtime behavior

- `is_available()` returns `true`.
- `start()` returns a new in-memory `FixtureBrowserSession`.
- `connect()` returns a new in-memory `FixtureBrowserSession` with the same
  provider-neutral interface.
- `new_page(url)` and `goto(url)` update a synthetic page URL.
- `title()`, `content()`, `evaluate()`, `screenshot()`, and `list_pages()` are
  deterministic and side-effect-light.

This package is intentionally not a stealth browser and should not be used for
real target browsing. Real browser integrations should use the template package
or their own package and register through the same entry-point group.
