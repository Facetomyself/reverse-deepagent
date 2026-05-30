# reverse-deepagent-legacy-mcp

Optional legacy JSReverser MCP runtime backend plugin for `reverse-deepagent`.

This package exposes the `legacy-mcp` runtime backend through the
`reverse_deepagent.runtime_backends` Python entry-point group. It is the
package-level split seam for keeping MCP compatibility installable without
making it the long-term Web runtime architecture center.

Current migration note: the implementation delegates to
`reverse_deepagent.runtime.legacy_mcp` while the compatibility backend is still
shipped in the core distribution. A later release can move the implementation
fully into this package and leave the core package with install guidance only.
