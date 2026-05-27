from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from reverse_deepagent.rebuild import write_rebuild_bundle
from reverse_deepagent.schemas import FinalResult, TaskCard


RebuildTool = Callable[..., dict[str, Any]]


def make_build_rebuild_delivery_tool(default_artifact_root: str | Path) -> RebuildTool:
    """Create a tool wrapper that generates rebuild delivery artifacts."""

    root = Path(default_artifact_root)

    def build_rebuild_delivery(
        task_card_json: str,
        final_result_json: str,
        artifact_root: str | None = None,
    ) -> dict[str, Any]:
        """Generate rebuild-plan and delivery files from a validated final result."""

        task_card = TaskCard.model_validate_json(task_card_json)
        final_result = FinalResult.model_validate_json(final_result_json)
        target_root = Path(artifact_root) if artifact_root else root
        return write_rebuild_bundle(target_root, task_card, final_result).model_dump(mode="json")

    build_rebuild_delivery.__name__ = "build_rebuild_delivery"
    build_rebuild_delivery.__doc__ = (
        "Generate rebuild-plan.json plus sign_rebuild.py, replay_demo.py, and scrapy_middleware.py. "
        "Inputs must be JSON strings generated from TaskCard and FinalResult. "
        "artifact_root is optional; when omitted, the agent default artifact root is used."
    )
    return build_rebuild_delivery
