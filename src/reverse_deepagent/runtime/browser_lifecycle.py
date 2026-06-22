"""Chrome browser lifecycle management for the reverse coordinator pipeline."""

from __future__ import annotations

from reverse_deepagent.runtime.chrome import ChromeCommandResult, ChromeDebugConfig, ensure_chrome_debug, stop_chrome_debug
from reverse_deepagent.runtime.legacy_mcp import is_legacy_mcp_runtime_kind


def launch_browser_if_legacy_mcp(
    runtime_kind: str,
    chrome_config: ChromeDebugConfig | None,
    ensure_chrome: bool,
    keep_chrome: bool,
) -> tuple[ChromeCommandResult | None, bool]:
    """Launch Chrome debug session if the runtime requires legacy MCP.

    Returns ``(chrome_launch, should_stop_chrome)`` where *should_stop_chrome*
    is ``True`` when Chrome was launched successfully and *keep_chrome*
    is ``False``, indicating the caller should stop Chrome during cleanup.
    """
    chrome_launch = None
    should_stop_chrome = False
    if is_legacy_mcp_runtime_kind(runtime_kind) and ensure_chrome:
        chrome_launch = ensure_chrome_debug(chrome_config)
        if not chrome_launch.ok:
            raise RuntimeError(
                f"Failed to ensure Chrome debug session: {chrome_launch.stderr or chrome_launch.stdout}"
            )
        should_stop_chrome = not keep_chrome
    return chrome_launch, should_stop_chrome


def stop_browser_if_needed(
    chrome_config: ChromeDebugConfig | None,
    should_stop_chrome: bool,
) -> ChromeCommandResult | None:
    """Stop the Chrome debug session if *should_stop_chrome* is set.

    Returns the ``ChromeCommandResult`` from the stop command, or ``None``
    if no stop was attempted.
    """
    if should_stop_chrome:
        return stop_chrome_debug(chrome_config)
    return None
