from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.tools.timeline_tools import make_review_flow_timeline_tool
from reverse_deepagent.tools.artifact_tools import make_read_workspace_artifact_tool

TIMELINE_SUBAGENT_NAME = "timeline"
TIMELINE_SUBAGENT_DESCRIPTION = "审计 flow timeline、correlation groups、stitch proposals 和 auto-stitch gate，只做 read-only timeline review。"


def load_timeline_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "timeline.txt"
    return path.read_text(encoding="utf-8")


def build_timeline_subagent(
    artifact_root: str | Path | None = None,
    prompt_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root) if artifact_root is not None else Path("artifacts")
    return {
        "name": TIMELINE_SUBAGENT_NAME,
        "description": TIMELINE_SUBAGENT_DESCRIPTION,
        "system_prompt": load_timeline_prompt(prompt_path),
        "tools": [make_read_workspace_artifact_tool(root), make_review_flow_timeline_tool()],
    }
