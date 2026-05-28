from __future__ import annotations

import json
from typing import Any, Callable

from reverse_deepagent.runtime.base import WebReverseRuntime
from reverse_deepagent.schemas import RouterResult, TaskCard


ReconTool = Callable[..., dict[str, Any]]


def make_run_web_recon_tool(runtime: WebReverseRuntime) -> ReconTool:
    """Create a tool wrapper that runs Web recon through the runtime adapter."""

    def run_web_recon(task_card_json: str, route_result_json: str) -> dict[str, Any]:
        task_card = TaskCard.model_validate_json(task_card_json)
        route_result = RouterResult.model_validate_json(route_result_json)
        return runtime.run_web_recon(task_card=task_card, route_result=route_result).model_dump(mode="json")

    run_web_recon.__name__ = "run_web_recon"
    run_web_recon.__doc__ = (
        "Run the minimal Web recon flow using the runtime adapter. "
        "Both inputs must be JSON strings generated from TaskCard and RouterResult."
    )
    return run_web_recon


def dump_model_json(payload: Any) -> str:
    """Serialize pydantic-like payloads or plain dictionaries into compact JSON strings."""

    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False)
