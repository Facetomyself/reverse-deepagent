from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.schemas import RebuildResult
from reverse_deepagent.tools.rebuild_tools import make_build_rebuild_delivery_tool

DELIVERY_SUBAGENT_NAME = "rebuild_delivery"
DELIVERY_SUBAGENT_DESCRIPTION = "将已验证候选函数交付为 rebuild-plan、纯 Python sign 脚本、HTTP replay demo 与可运行 Scrapy replay 项目。"


def load_delivery_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "delivery.txt"
    return path.read_text(encoding="utf-8")


def build_delivery_subagent(
    artifact_root: str | Path,
    prompt_path: str | Path | None = None,
) -> dict[str, Any]:
    return {
        "name": DELIVERY_SUBAGENT_NAME,
        "description": DELIVERY_SUBAGENT_DESCRIPTION,
        "system_prompt": load_delivery_prompt(prompt_path),
        "tools": [make_build_rebuild_delivery_tool(artifact_root)],
        "response_format": RebuildResult,
    }
