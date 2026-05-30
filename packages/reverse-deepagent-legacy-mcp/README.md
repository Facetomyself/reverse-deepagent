# reverse-deepagent-legacy-mcp

Optional legacy JSReverser MCP runtime backend plugin for `reverse-deepagent`.

This package exposes the `legacy-mcp` runtime backend through the
`reverse_deepagent.runtime_backends` Python entry-point group. It is the
package-level split seam for keeping MCP compatibility installable without
making it the long-term Web runtime architecture center.

Current migration note: this package owns the legacy MCP runtime
registration and factory implementation. The core package keeps only a
compatibility shim, alias warning, plugin delegation, and install guidance; it
no longer ships a built-in legacy MCP factory fallback.
