from __future__ import annotations

from typing import Any, Callable

from reverse_deepagent.runtime.base import ReverseRuntime


BrowserTool = Callable[..., dict[str, Any]]


def make_ensure_browser_session_tool(runtime: ReverseRuntime) -> BrowserTool:
    """Create a tool wrapper that exposes normalized browser session state."""

    def ensure_browser_session() -> dict[str, Any]:
        return runtime.ensure_browser_session().model_dump(mode="json")

    ensure_browser_session.__name__ = "ensure_browser_session"
    ensure_browser_session.__doc__ = "Ensure the browser session is reachable and return normalized session state."
    return ensure_browser_session
