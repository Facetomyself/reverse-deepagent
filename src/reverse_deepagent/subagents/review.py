from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.review_gate import ReviewGateResult
from reverse_deepagent.tools.review_tools import make_evaluate_review_gate_tool

REVIEW_SUBAGENT_NAME = "review"
REVIEW_SUBAGENT_DESCRIPTION = "交付前复核 evidence promotion、review hints 和 review gate，只做 read-only gate 评估。"


def load_review_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "review.txt"
    return path.read_text(encoding="utf-8")


def build_review_subagent(prompt_path: str | Path | None = None) -> dict[str, Any]:
    return {
        "name": REVIEW_SUBAGENT_NAME,
        "description": REVIEW_SUBAGENT_DESCRIPTION,
        "system_prompt": load_review_prompt(prompt_path),
        "tools": [make_evaluate_review_gate_tool()],
        "response_format": ReviewGateResult,
    }
