from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.tools.review_tools import make_evaluate_review_gate_tool, make_record_review_approval_tool

REVIEW_SUBAGENT_NAME = "review"
REVIEW_SUBAGENT_DESCRIPTION = "交付前复核 evidence promotion、review hints、review gate 和显式人工审批审计。"


def load_review_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "review.txt"
    return path.read_text(encoding="utf-8")


def build_review_subagent(
    artifact_root: str | Path | None = None,
    prompt_path: str | Path | None = None,
) -> dict[str, Any]:
    review_root = Path(artifact_root) / "workspace" if artifact_root is not None else Path("artifacts") / "workspace"
    return {
        "name": REVIEW_SUBAGENT_NAME,
        "description": REVIEW_SUBAGENT_DESCRIPTION,
        "system_prompt": load_review_prompt(prompt_path),
        "tools": [make_evaluate_review_gate_tool(), make_record_review_approval_tool(review_root)],
    }
