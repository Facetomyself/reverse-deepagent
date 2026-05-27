from __future__ import annotations

import json
from typing import Any, Callable

from reverse_deepagent.runtime.base import ReverseRuntime


ProtectionTool = Callable[..., dict[str, Any]]


def make_apply_minimal_protection_tool(runtime: ReverseRuntime) -> ProtectionTool:
    """Create a tool wrapper that applies a minimal protection patch."""

    def apply_minimal_protection(protection_name: str, context_json: str = "{}") -> dict[str, Any]:
        context = json.loads(context_json) if context_json else {}
        return runtime.apply_minimal_protection(protection_name=protection_name, context=context).model_dump(mode="json")

    apply_minimal_protection.__name__ = "apply_minimal_protection"
    apply_minimal_protection.__doc__ = (
        "Apply the minimal protection patch for a blocked reverse task. "
        "context_json must be a JSON object string."
    )
    return apply_minimal_protection
