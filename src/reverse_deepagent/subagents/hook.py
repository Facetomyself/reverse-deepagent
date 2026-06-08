from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.tools.hook_tools import make_record_source_map_selected_executor_approval_tool, make_review_hook_artifacts_tool
from reverse_deepagent.tools.artifact_tools import make_read_workspace_artifact_tool

HOOK_SUBAGENT_NAME = "hook"
HOOK_SUBAGENT_DESCRIPTION = "审计 function / module hook inventory、hook timelines、source-logpoint artifacts、Source Map follow-through approval records 和 reviewed source-logpoint install results。"


def load_hook_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "hook.txt"
    return path.read_text(encoding="utf-8")


def build_hook_subagent(
    artifact_root: str | Path | None = None,
    prompt_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root) if artifact_root is not None else Path("artifacts")
    return {
        "name": HOOK_SUBAGENT_NAME,
        "description": HOOK_SUBAGENT_DESCRIPTION,
        "system_prompt": load_hook_prompt(prompt_path),
        "tools": [
            make_read_workspace_artifact_tool(root),
            make_review_hook_artifacts_tool(root),
            make_record_source_map_selected_executor_approval_tool(root),
        ],
    }
