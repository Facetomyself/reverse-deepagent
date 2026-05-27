from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import ArtifactRef, ConfidenceLevel, ExecutionStatus, ReverseStage, SchemaBaseModel


class RebuildResult(SchemaBaseModel):
    """Structured result returned by the Rebuild / Delivery subagent."""

    status: ExecutionStatus = Field(description="Execution status for rebuild delivery.")
    stage: ReverseStage = Field(default=ReverseStage.REPLAY_DELIVERY, description="Current stage, normally replay-delivery.")
    rebuild_plan: dict[str, Any] = Field(default_factory=dict, description="Normalized rebuild plan generated from validated candidates.")
    generated_files: dict[str, str] = Field(default_factory=dict, description="Generated delivery files keyed by logical name.")
    artifacts: list[ArtifactRef] = Field(default_factory=list, description="Artifacts generated for rebuild delivery.")
    next_action: str = Field(description="Recommended immediate next action.")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM, description="Confidence in rebuild delivery result.")
