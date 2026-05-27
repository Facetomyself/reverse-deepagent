from __future__ import annotations

from typing import Any, Callable

from reverse_deepagent.runtime.base import ReverseRuntime
from reverse_deepagent.schemas import FinalResult


ArtifactTool = Callable[..., dict[str, Any]]


def make_export_reverse_artifacts_tool(runtime: ReverseRuntime) -> ArtifactTool:
    """Create a tool wrapper that exports runtime artifacts."""

    def export_reverse_artifacts(final_result_json: str | None = None) -> dict[str, Any]:
        final_result = FinalResult.model_validate_json(final_result_json) if final_result_json else None
        return runtime.export_reverse_artifacts(final_result=final_result).model_dump(mode="json")

    export_reverse_artifacts.__name__ = "export_reverse_artifacts"
    export_reverse_artifacts.__doc__ = "Export runtime artifacts and return a normalized export bundle."
    return export_reverse_artifacts
