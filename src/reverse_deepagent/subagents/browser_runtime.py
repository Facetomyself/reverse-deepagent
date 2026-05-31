from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.runtime.base import WebReverseRuntime
from reverse_deepagent.tools.browser_tools import (
    make_browser_provider_matrix_tool,
    make_describe_browser_provider_tool,
    make_ensure_browser_session_tool,
)

BROWSER_RUNTIME_SUBAGENT_NAME = "browser_runtime"
BROWSER_RUNTIME_SUBAGENT_DESCRIPTION = "管理 BrowserProvider 能力发现、provider metadata 和浏览器会话健康检查，不执行 Web recon。"


def load_browser_runtime_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "browser_runtime.txt"
    return path.read_text(encoding="utf-8")


def build_browser_runtime_subagent(runtime: WebReverseRuntime | None = None, prompt_path: str | Path | None = None) -> dict[str, Any]:
    tools = [make_browser_provider_matrix_tool(), make_describe_browser_provider_tool()]
    if runtime is not None:
        tools.append(make_ensure_browser_session_tool(runtime))
    return {
        "name": BROWSER_RUNTIME_SUBAGENT_NAME,
        "description": BROWSER_RUNTIME_SUBAGENT_DESCRIPTION,
        "system_prompt": load_browser_runtime_prompt(prompt_path),
        "tools": tools,
    }
