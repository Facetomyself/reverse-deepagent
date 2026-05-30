from __future__ import annotations

from reverse_deepagent.runtime.legacy_mcp import legacy_mcp_backend_registration
from reverse_deepagent.runtime.registry import RuntimeBackendRegistration


def runtime_backend_registration() -> RuntimeBackendRegistration:
    """Return the optional legacy MCP backend registration.

    The entry point intentionally returns registration metadata and a backend
    factory without starting JSReverser MCP, Chrome, or any network session.
    """

    return legacy_mcp_backend_registration()


__all__ = ["runtime_backend_registration"]
