from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.tools.hook_tools import make_review_hook_artifacts_tool

HOOK_SUBAGENT_NAME = "hook"
HOOK_SUBAGENT_DESCRIPTION = "审计 function / module hook inventory、hook timelines 和 source-logpoint artifacts，只做 read-only hook artifact review。"


def load_hook_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "hook.txt"
    return path.read_text(encoding="utf-8")


def build_hook_subagent(prompt_path: str | Path | None = None) -> dict[str, Any]:
    return {
        "name": HOOK_SUBAGENT_NAME,
        "description": HOOK_SUBAGENT_DESCRIPTION,
        "system_prompt": load_hook_prompt(prompt_path),
        "tools": [make_review_hook_artifacts_tool()],
    }
