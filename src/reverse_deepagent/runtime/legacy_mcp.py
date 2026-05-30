from __future__ import annotations

from importlib import import_module
from typing import Any, NoReturn

from reverse_deepagent.runtime.base import WebReverseRuntime
from reverse_deepagent.runtime.registry import RuntimeBackendRegistration

LEGACY_MCP_BACKEND_ID = "legacy-mcp"
LEGACY_MCP_ALIASES = ("mcp", "jsreverser-mcp")
LEGACY_MCP_PACKAGE = "reverse-deepagent-legacy-mcp"
LEGACY_MCP_IMPORT_NAME = "reverse_deepagent_legacy_mcp"
LEGACY_MCP_ALIAS_DEPRECATION_WARNING = (
    "警告：`mcp` / `jsreverser-mcp` 只是 legacy 兼容别名，后续新脚本请改用 `legacy-mcp`；"
    "Web 默认路径请优先使用 `native-web`。"
)


class LegacyMcpPluginUnavailableError(ValueError):
    """Raised when the optional legacy MCP backend package is not installed."""


def legacy_mcp_install_guidance() -> dict[str, Any]:
    """Return structured guidance for enabling the optional legacy MCP backend."""

    return {
        "error": "legacy_mcp_optional_backend_not_installed",
        "backend_id": LEGACY_MCP_BACKEND_ID,
        "aliases": list(LEGACY_MCP_ALIASES),
        "package": LEGACY_MCP_PACKAGE,
        "import_name": LEGACY_MCP_IMPORT_NAME,
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


def legacy_mcp_missing_plugin_message(runtime_kind: str = LEGACY_MCP_BACKEND_ID) -> str:
    """Return a stable human-readable missing-plugin message."""

    guidance = legacy_mcp_install_guidance()
    return (
        f"Legacy MCP runtime backend {runtime_kind!r} is optional and is not installed in the core package. "
        f"{guidance['install_hint']}. Preferred Web runtime: {guidance['preferred_web_runtime']}."
    )


def _raise_missing_plugin(runtime_kind: str = LEGACY_MCP_BACKEND_ID) -> NoReturn:
    raise LegacyMcpPluginUnavailableError(legacy_mcp_missing_plugin_message(runtime_kind))


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
    _raise_missing_plugin()


def legacy_mcp_backend_registration() -> RuntimeBackendRegistration:
    """Return legacy MCP registration, preferring the optional plugin implementation."""

    plugin = _plugin_module()
    if plugin is not None and hasattr(plugin, "runtime_backend_registration"):
        return plugin.runtime_backend_registration()
    _raise_missing_plugin()


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
