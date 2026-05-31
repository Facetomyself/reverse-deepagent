from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.schemas import RebuildResult
from reverse_deepagent.tools.rebuild_tools import make_build_rebuild_delivery_tool, make_review_rebuild_artifacts_tool

REBUILD_SUBAGENT_NAME = "rebuild"
REBUILD_SUBAGENT_DESCRIPTION = "生成并复核 rebuild-plan、pure/context-aware replay、Scrapy project 和 rebuild artifacts，交付执行留给 delivery。"


def load_rebuild_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "rebuild.txt"
    return path.read_text(encoding="utf-8")


def build_rebuild_subagent(
    artifact_root: str | Path,
    prompt_path: str | Path | None = None,
) -> dict[str, Any]:
    return {
        "name": REBUILD_SUBAGENT_NAME,
        "description": REBUILD_SUBAGENT_DESCRIPTION,
        "system_prompt": load_rebuild_prompt(prompt_path),
        "tools": [make_build_rebuild_delivery_tool(artifact_root), make_review_rebuild_artifacts_tool()],
        "response_format": RebuildResult,
    }
