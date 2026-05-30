from __future__ import annotations

from typing import Any

from pydantic import Field

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.runtime.base import RuntimeBackendCapabilities, WebReverseRuntime
from reverse_deepagent.runtime.registry import RuntimeBackendRegistration
from reverse_deepagent.schemas import SchemaBaseModel

from .mcp_stdio import McpBridgeError, StdioMcpBridge

LEGACY_MCP_BACKEND_ID = "legacy-mcp"
LEGACY_MCP_ALIASES = ("mcp", "jsreverser-mcp")
DEFAULT_JSREVERSER_MCP_COMMAND = "/opt/homebrew/bin/jsreverser-mcp"
DEFAULT_REMOTE_DEBUGGING_URL = "http://127.0.0.1:9222"
LEGACY_MCP_ALIAS_DEPRECATION_WARNING = (
    "警告：`mcp` / `jsreverser-mcp` 只是 legacy 兼容别名，后续新脚本请改用 `legacy-mcp`；"
    "Web 默认路径请优先使用 `native-web`。"
)


class JSReverserMcpConfig(SchemaBaseModel):
    """Serializable configuration for the optional JSReverser MCP backend."""

    command: str = Field(default=DEFAULT_JSREVERSER_MCP_COMMAND)
    browser_url: str = Field(default=DEFAULT_REMOTE_DEBUGGING_URL)
    request_timeout: float = 30.0
    startup_timeout: float = 15.0
    backend_id: str = LEGACY_MCP_BACKEND_ID
    display_name: str = "Legacy JSReverser MCP"
    transport: str = "mcp-stdio"
    default_page_size: int = 20
    post_navigation_wait_seconds: float = 0.5
    runtime_context_sample_count: int = 3
    runtime_context_sample_interval_seconds: float = 0.05

    def bridge_command(self) -> list[str]:
        return [self.command, "--browserUrl", self.browser_url]

    def debug_summary(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def create_jsreverser_mcp_runtime(
    *,
    config: JSReverserMcpConfig | None = None,
    command: str | None = None,
    browser_url: str | None = None,
    request_timeout: float | None = None,
    startup_timeout: float | None = None,
    backend_id: str | None = None,
    display_name: str | None = None,
    transport: str | None = None,
) -> JSReverserRuntime:
    """Create a JSReverser runtime backed by a real stdio MCP process."""

    config = config or JSReverserMcpConfig()
    config = config.model_copy(
        update={
            key: value
            for key, value in {
                "command": command,
                "browser_url": browser_url,
                "request_timeout": request_timeout,
                "startup_timeout": startup_timeout,
                "backend_id": backend_id,
                "display_name": display_name,
                "transport": transport,
            }.items()
            if value is not None
        }
    )
    bridge = StdioMcpBridge(
        command=config.bridge_command(),
        request_timeout=config.request_timeout,
        startup_timeout=config.startup_timeout,
    )
    return JSReverserRuntime(
        bridge=bridge,
        backend_id=config.backend_id,
        display_name=config.display_name,
        transport=config.transport,
        default_page_size=config.default_page_size,
        post_navigation_wait_seconds=config.post_navigation_wait_seconds,
        runtime_context_sample_count=config.runtime_context_sample_count,
        runtime_context_sample_interval_seconds=config.runtime_context_sample_interval_seconds,
        backend_config=config.debug_summary(),
    )


def create_legacy_mcp_runtime(
    *,
    browser_url: str | None = None,
    mcp_command: str | None = None,
    **kwargs: Any,
) -> WebReverseRuntime:
    """Create the optional legacy JSReverser MCP runtime backend.

    The core runtime registry passes a shared kwargs bag used by other Web
    backends. Legacy MCP intentionally consumes only its own configuration and
    ignores unrelated BrowserProvider / lightweight-backend options.
    """

    config = JSReverserMcpConfig(
        command=mcp_command or kwargs.get("command") or DEFAULT_JSREVERSER_MCP_COMMAND,
        browser_url=browser_url or DEFAULT_REMOTE_DEBUGGING_URL,
        request_timeout=kwargs.get("request_timeout") or 30.0,
        startup_timeout=kwargs.get("startup_timeout") or 15.0,
        backend_id=LEGACY_MCP_BACKEND_ID,
        display_name="Legacy JSReverser MCP",
        transport="mcp-stdio",
    )
    return create_jsreverser_mcp_runtime(config=config)


def check_legacy_mcp_tools(
    *,
    command: str = DEFAULT_JSREVERSER_MCP_COMMAND,
    browser_url: str = DEFAULT_REMOTE_DEBUGGING_URL,
    request_timeout: float = 10.0,
    startup_timeout: float = 10.0,
) -> dict[str, Any]:
    """Start a legacy MCP stdio process and run the minimal doctor probes."""

    bridge = StdioMcpBridge(
        command=[command, "--browserUrl", browser_url],
        request_timeout=request_timeout,
        startup_timeout=startup_timeout,
    )
    try:
        with bridge:
            tools = bridge.list_tools()
            health = bridge.invoke("check_browser_health", {})
        tool_names = [item.get("name") for item in tools.get("tools", []) if isinstance(item, dict)]
        return {
            "ok": True,
            "tool_count": len(tool_names),
            "tool_sample": tool_names[:20],
            "health": health,
        }
    except (McpBridgeError, OSError, RuntimeError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "stderr": bridge.get_stderr()[-2000:],
        }


def runtime_backend_registration() -> RuntimeBackendRegistration:
    """Return the optional legacy MCP backend registration.

    The entry point intentionally returns registration metadata and a backend
    factory without starting JSReverser MCP, Chrome, or any network session.
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
            config={
                "default_command": DEFAULT_JSREVERSER_MCP_COMMAND,
                "aliases": list(LEGACY_MCP_ALIASES),
                "package": "reverse-deepagent-legacy-mcp",
            },
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


legacy_mcp_backend_registration = runtime_backend_registration

__all__ = [
    "DEFAULT_JSREVERSER_MCP_COMMAND",
    "DEFAULT_REMOTE_DEBUGGING_URL",
    "JSReverserMcpConfig",
    "LEGACY_MCP_ALIASES",
    "LEGACY_MCP_ALIAS_DEPRECATION_WARNING",
    "LEGACY_MCP_BACKEND_ID",
    "McpBridgeError",
    "StdioMcpBridge",
    "check_legacy_mcp_tools",
    "create_jsreverser_mcp_runtime",
    "create_legacy_mcp_runtime",
    "is_legacy_mcp_runtime_kind",
    "legacy_mcp_alias_warning",
    "legacy_mcp_backend_registration",
    "runtime_backend_registration",
]
