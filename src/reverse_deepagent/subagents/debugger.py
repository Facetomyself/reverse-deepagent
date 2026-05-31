from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.tools.debugger_tools import make_review_debugger_artifacts_tool
from reverse_deepagent.tools.artifact_tools import make_read_workspace_artifact_tool

DEBUGGER_SUBAGENT_NAME = "debugger"
DEBUGGER_SUBAGENT_DESCRIPTION = "审计 debugger paused-session、callframes、continuation preflight 和调试时间线，只做 read-only debugger artifact review。"


def load_debugger_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "debugger.txt"
    return path.read_text(encoding="utf-8")


def build_debugger_subagent(
    artifact_root: str | Path | None = None,
    prompt_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root) if artifact_root is not None else Path("artifacts")
    return {
        "name": DEBUGGER_SUBAGENT_NAME,
        "description": DEBUGGER_SUBAGENT_DESCRIPTION,
        "system_prompt": load_debugger_prompt(prompt_path),
        "tools": [make_read_workspace_artifact_tool(root), make_review_debugger_artifacts_tool(root)],
    }
