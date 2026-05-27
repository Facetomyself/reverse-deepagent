# Roadmap

This roadmap is intentionally pragmatic: stabilize the Web / JS pipeline first, then open extension points for other runtimes.

## v0.1.x - Public demo stabilization

Focus: keep the current Web / JS demo reliable and maintainable.

- Keep public CI green for mock and pure-Python flows.
- Improve README examples and troubleshooting.
- Add more fixture coverage for common signing patterns.
- Expand context-aware rebuild tests.
- Document JSReverser MCP setup assumptions.

## v0.2.x - Runtime adapter pluginization

Focus: make runtime backends easier to swap without changing agent orchestration.

- Formalize runtime adapter contracts.
- Split MCP, CLI, and browser automation backends behind a shared interface.
- Add capability discovery for each backend.
- Add typed artifact manifests for backend outputs.
- Add self-hosted/manual CI for real MCP smoke tests.

## v0.3.x - Algorithm strategy library

Focus: grow from fixture strategies to a reusable strategy registry.

- Add pluggable strategy detectors.
- Add confidence and evidence scoring per strategy.
- Add generated code review hints.
- Add multi-sample runtime context stability diff.
- Add WASM / VM / obfuscation triage hooks.

## v0.4.x - Multi-platform expansion planning

Focus: preserve a clean path toward non-Web runtimes.

- Draft Android adapter interface.
- Draft iOS adapter interface.
- Draft mini-program adapter interface.
- Define artifact schemas that are not browser-specific.
- Keep Web-specific assumptions isolated under Web runtime packages.
