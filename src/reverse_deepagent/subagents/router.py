from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.schemas import RouterResult
from reverse_deepagent.tools.route_tools import DEFAULT_JS_REVERSE_SKILL_ROOT, route_reverse_task

ROUTER_SUBAGENT_NAME = "router"
ROUTER_SUBAGENT_DESCRIPTION = "根据 Reverse Task Card 与 js-reverse manifests 选择 mode、playbook、initial stage 和 next_action。"


def load_router_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "router.txt"
    return path.read_text(encoding="utf-8")


def build_router_subagent(skill_root: str | None = None, prompt_path: str | Path | None = None) -> dict[str, Any]:
    effective_skill_root = skill_root or str(DEFAULT_JS_REVERSE_SKILL_ROOT)

    def route_reverse_task_tool(task_text: str) -> dict[str, Any]:
        """Route a reverse task using js-reverse manifests and route policy."""
        return route_reverse_task(task_text=task_text, skill_root=effective_skill_root)

    route_reverse_task_tool.__name__ = "route_reverse_task"
    return {
        "name": ROUTER_SUBAGENT_NAME,
        "description": ROUTER_SUBAGENT_DESCRIPTION,
        "system_prompt": load_router_prompt(prompt_path),
        "tools": [route_reverse_task_tool],
        "response_format": RouterResult,
    }
