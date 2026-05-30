from __future__ import annotations

from importlib import import_module
from typing import Any

from reverse_deepagent.runtime.base import RuntimeBackendCapabilities, WebReverseRuntime
from reverse_deepagent.runtime.registry import RuntimeBackendRegistration

LEGACY_MCP_BACKEND_ID = "legacy-mcp"
LEGACY_MCP_ALIASES = ("mcp", "jsreverser-mcp")
LEGACY_MCP_PACKAGE = "reverse-deepagent-legacy-mcp"
LEGACY_MCP_IMPORT_NAME = "reverse_deepagent_legacy_mcp"
LEGACY_MCP_ALIAS_DEPRECATION_WARNING = (
    "警告：`mcp` / `jsreverser-mcp` 只是 legacy 兼容别名，后续新脚本请改用 `legacy-mcp`；"
    "Web 默认路径请优先使用 `native-web`。"
)


def legacy_mcp_install_guidance() -> dict[str, Any]:
    """Return structured guidance for enabling the optional legacy MCP backend."""

    return {
        "backend_id": LEGACY_MCP_BACKEND_ID,
        "package": LEGACY_MCP_PACKAGE,
        "entry_point_group": "reverse_deepagent.runtime_backends",
        "entry_point": "legacy-mcp = reverse_deepagent_legacy_mcp:runtime_backend_registration",
        "install_hint": f'Install the optional package, for example: uv pip install -e "packages/{LEGACY_MCP_PACKAGE}"',
        "runtime_hint": "Use --runtime legacy-mcp only when JSReverser MCP and a Chrome DevTools endpoint are required.",
        "preferred_web_runtime": "native-web",
    }


def _plugin_module() -> Any | None:
    try:
        return import_module(LEGACY_MCP_IMPORT_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == LEGACY_MCP_IMPORT_NAME:
            return None
        raise


def _builtin_compat_create_legacy_mcp_runtime(
    *,
    browser_url: str | None = None,
    mcp_command: str | None = None,
    **_: Any,
) -> WebReverseRuntime:
    from reverse_deepagent.adapters.jsreverser import (
        DEFAULT_JSREVERSER_MCP_COMMAND,
        JSReverserMcpConfig,
        create_jsreverser_mcp_runtime,
    )

    config = JSReverserMcpConfig(
        command=mcp_command or DEFAULT_JSREVERSER_MCP_COMMAND,
        browser_url=browser_url or "http://127.0.0.1:9222",
        backend_id=LEGACY_MCP_BACKEND_ID,
        display_name="Legacy JSReverser MCP",
        transport="mcp-stdio",
    )
    return create_jsreverser_mcp_runtime(config=config)


def _builtin_compat_legacy_mcp_backend_registration() -> RuntimeBackendRegistration:
    from reverse_deepagent.adapters.jsreverser import DEFAULT_JSREVERSER_MCP_COMMAND

    return RuntimeBackendRegistration(
        backend_id=LEGACY_MCP_BACKEND_ID,
        aliases=LEGACY_MCP_ALIASES,
        factory=_builtin_compat_create_legacy_mcp_runtime,
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
                "built-in compatibility fallback; prefer the reverse-deepagent-legacy-mcp optional package",
            ],
            config={
                "default_command": DEFAULT_JSREVERSER_MCP_COMMAND,
                "aliases": list(LEGACY_MCP_ALIASES),
                "compat_fallback": True,
                "install_guidance": legacy_mcp_install_guidance(),
            },
        ),
    )


def create_legacy_mcp_runtime(
    *,
    browser_url: str | None = None,
    mcp_command: str | None = None,
    **kwargs: Any,
) -> WebReverseRuntime:
    """Create the legacy MCP runtime through the optional plugin when available."""

    plugin = _plugin_module()
    if plugin is not None and hasattr(plugin, "create_legacy_mcp_runtime"):
        return plugin.create_legacy_mcp_runtime(browser_url=browser_url, mcp_command=mcp_command, **kwargs)
    return _builtin_compat_create_legacy_mcp_runtime(browser_url=browser_url, mcp_command=mcp_command, **kwargs)


def legacy_mcp_backend_registration() -> RuntimeBackendRegistration:
    """Return legacy MCP registration, preferring the optional plugin implementation."""

    plugin = _plugin_module()
    if plugin is not None and hasattr(plugin, "runtime_backend_registration"):
        return plugin.runtime_backend_registration()
    return _builtin_compat_legacy_mcp_backend_registration()


def legacy_mcp_alias_warning(runtime_kind: str) -> str | None:
    """Return the deprecation warning for legacy MCP aliases, if applicable."""

    if runtime_kind in LEGACY_MCP_ALIASES:
        plugin = _plugin_module()
        if plugin is not None and hasattr(plugin, "legacy_mcp_alias_warning"):
            return plugin.legacy_mcp_alias_warning(runtime_kind)
        return LEGACY_MCP_ALIAS_DEPRECATION_WARNING
    return None


def is_legacy_mcp_runtime_kind(runtime_kind: str) -> bool:
    """Return whether a runtime id or alias refers to legacy MCP."""

    return runtime_kind in {LEGACY_MCP_BACKEND_ID, *LEGACY_MCP_ALIASES}
