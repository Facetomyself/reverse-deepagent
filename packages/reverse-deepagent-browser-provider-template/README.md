# reverse-deepagent-browser-provider-template

Template BrowserProvider plugin package for `reverse-deepagent`.

This package shows the minimum shape for adding a replaceable browser provider
without changing the core runtime. Copy it when integrating a custom browser,
anti-detect browser, hosted CDP service, or vendor SDK.

## Entry point

The package exposes one registration through the
`reverse_deepagent.browser_providers` Python entry-point group:

```toml
[project.entry-points."reverse_deepagent.browser_providers"]
template-browser = "reverse_deepagent_browser_provider_template:browser_provider_registration"
```

`browser_provider_registration()` returns a `BrowserProviderRegistration` with
serializable, non-secret capabilities and a provider factory. Loading metadata
must not launch browsers, probe CDP, import heavy optional binaries, or call the
factory.

## Replace these pieces

- Change `TEMPLATE_BROWSER_PROVIDER_ID` and aliases.
- Replace `TemplateBrowserProvider.start()` / `connect()` with real lifecycle
  code.
- Replace `TemplateBrowserSession` and `TemplateBrowserPage` with adapters for
  your browser SDK.
- Keep `describe()` side-effect free and never put tokens, cookies, passwords,
  proxy credentials, or raw headers in capability metadata.

The default template intentionally raises `BrowserProviderUnavailableError` from
`start()` and `connect()` so a copied package cannot accidentally pretend that a
real browser integration is complete.
