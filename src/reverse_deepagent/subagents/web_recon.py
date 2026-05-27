from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.runtime.base import ReverseRuntime
from reverse_deepagent.schemas import ReconResult
from reverse_deepagent.tools.browser_tools import make_ensure_browser_session_tool
from reverse_deepagent.tools.recon_tools import make_run_web_recon_tool

WEB_RECON_SUBAGENT_NAME = "web_recon"
WEB_RECON_SUBAGENT_DESCRIPTION = "执行 Web 逆向首阶段侦察，包括浏览器会话检查、页面侦察、网络样本观察和源码搜索。"


def load_web_recon_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "web_recon.txt"
    return path.read_text(encoding="utf-8")


def build_web_recon_subagent(runtime: ReverseRuntime, prompt_path: str | Path | None = None) -> dict[str, Any]:
    return {
        "name": WEB_RECON_SUBAGENT_NAME,
        "description": WEB_RECON_SUBAGENT_DESCRIPTION,
        "system_prompt": load_web_recon_prompt(prompt_path),
        "tools": [make_ensure_browser_session_tool(runtime), make_run_web_recon_tool(runtime)],
        "response_format": ReconResult,
    }
