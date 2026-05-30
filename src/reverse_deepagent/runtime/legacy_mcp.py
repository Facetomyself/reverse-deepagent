from __future__ import annotations

from typing import Any

from reverse_deepagent.adapters.jsreverser import (
    DEFAULT_JSREVERSER_MCP_COMMAND,
    JSReverserMcpConfig,
    create_jsreverser_mcp_runtime,
)
from reverse_deepagent.runtime.base import RuntimeBackendCapabilities, WebReverseRuntime
from reverse_deepagent.runtime.registry import RuntimeBackendRegistration

LEGACY_MCP_BACKEND_ID = "legacy-mcp"
LEGACY_MCP_ALIASES = ("mcp", "jsreverser-mcp")
LEGACY_MCP_ALIAS_DEPRECATION_WARNING = (
    "警告：`mcp` / `jsreverser-mcp` 只是 legacy 兼容别名，后续新脚本请改用 `legacy-mcp`；"
    "Web 默认路径请优先使用 `native-web`。"
)


def create_legacy_mcp_runtime(
    *,
    browser_url: str | None = None,
    mcp_command: str | None = None,
    **_: Any,
) -> WebReverseRuntime:
    """Create the legacy JSReverser MCP runtime backend.

    This function is deliberately outside the coordinator so the MCP-backed
    runtime can become an optional package / entry-point plugin without leaking
    MCP command, browser URL, or backend capability details into orchestration
    code.
    """

    config = JSReverserMcpConfig(
        command=mcp_command or DEFAULT_JSREVERSER_MCP_COMMAND,
        browser_url=browser_url or "http://127.0.0.1:9222",
        backend_id=LEGACY_MCP_BACKEND_ID,
        display_name="Legacy JSReverser MCP",
        transport="mcp-stdio",
    )
    return create_jsreverser_mcp_runtime(config=config)


def legacy_mcp_backend_registration() -> RuntimeBackendRegistration:
    """Return the legacy MCP backend registration.

    The return shape is intentionally the same object expected by
    `reverse_deepagent.runtime_backends` entry-point plugins.
    """

    return RuntimeBackendRegistration(
        backend_id=LEGACY_MCP_BACKEND_ID,
        aliases=LEGACY_MCP_ALIASES,
        factory=create_legacy_mcp_runtime,
        capabilities=RuntimeBackendCapabilities(
            backend_id=LEGACY_MCP_BACKEND_ID,
            display_name="Legacy JSReverser MCP",
            transport="mcp-stdio",
            target_platforms=["web"],
            supports_browser_session=True,
            supports_web_recon=True,
            supports_protection_patch=True,
            supports_artifact_export=True,
            supports_runtime_context=True,
            supports_replay_validation=True,
            managed_chrome=True,
            mcp_backed=True,
            evidence_kinds=["request", "callstack", "static", "dynamic", "storage", "note"],
            artifact_kinds=["json", "export", "rebuild", "markdown"],
            notes=[
                "legacy compatibility backend backed by jsreverser-mcp",
                "requires jsreverser-mcp and a reachable Chrome DevTools endpoint",
                "mcp and jsreverser-mcp remain deprecated temporary compatibility aliases",
            ],
            config={"default_command": DEFAULT_JSREVERSER_MCP_COMMAND, "aliases": list(LEGACY_MCP_ALIASES)},
        ),
    )


def legacy_mcp_alias_warning(runtime_kind: str) -> str | None:
    """Return the deprecation warning for legacy MCP aliases, if applicable."""

    if runtime_kind in LEGACY_MCP_ALIASES:
        return LEGACY_MCP_ALIAS_DEPRECATION_WARNING
    return None


def is_legacy_mcp_runtime_kind(runtime_kind: str) -> bool:
    """Return whether a runtime id or alias refers to legacy MCP."""

    return runtime_kind in {LEGACY_MCP_BACKEND_ID, *LEGACY_MCP_ALIASES}
