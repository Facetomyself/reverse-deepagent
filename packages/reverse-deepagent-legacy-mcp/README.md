# reverse-deepagent-legacy-mcp

Optional legacy JSReverser MCP runtime backend plugin for `reverse-deepagent`.

This package exposes the `legacy-mcp` runtime backend through the
`reverse_deepagent.runtime_backends` Python entry-point group. It is the
package-level split seam for keeping MCP compatibility installable without
making it the long-term Web runtime architecture center.

Current migration note: this package now owns the legacy MCP runtime
registration and factory implementation. The core package still ships a
compatibility shim and built-in fallback for the transition window; a later
release can remove that fallback and leave the core package with install
guidance only.
