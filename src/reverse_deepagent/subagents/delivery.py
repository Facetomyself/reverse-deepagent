from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.tools.delivery_tools import (
    make_delivery_recovery_executor_tool,
    make_delivery_rollback_executor_tool,
    make_delivery_resume_planner_tool,
    make_delivery_resume_runner_tool,
    make_delivery_resume_workflow_scheduler_tool,
    make_delivery_rollback_state_writer_tool,
    make_delivery_transaction_lock_provider_tool,
    make_delivery_transition_executor_tool,
    make_local_delivery_executor_tool,
)

DELIVERY_SUBAGENT_NAME = "delivery"
DELIVERY_SUBAGENT_DESCRIPTION = "将已 review 的 rebuild / report artifacts 执行为本地交付、manifest mutation 或 external delivery transaction。"


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
        "tools": [
            make_local_delivery_executor_tool(Path(artifact_root) / "delivery"),
            make_delivery_resume_planner_tool(Path(artifact_root) / "delivery"),
            make_delivery_resume_runner_tool(Path(artifact_root) / "delivery"),
            make_delivery_resume_workflow_scheduler_tool(Path(artifact_root) / "delivery"),
            make_delivery_transaction_lock_provider_tool(Path(artifact_root) / "delivery"),
            make_delivery_transition_executor_tool(Path(artifact_root) / "delivery"),
            make_delivery_recovery_executor_tool(Path(artifact_root) / "delivery"),
            make_delivery_rollback_state_writer_tool(Path(artifact_root) / "delivery"),
            make_delivery_rollback_executor_tool(Path(artifact_root) / "delivery"),
        ],
    }
