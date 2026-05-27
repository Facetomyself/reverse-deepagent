from __future__ import annotations

from pydantic import Field

from .common import ArtifactRef, ConfidenceLevel, ExecutionStatus, SchemaBaseModel


class ProtectionResult(SchemaBaseModel):
    """Structured result returned by the Protection subagent."""

    protection_name: str = Field(description="Name of the applied or attempted protection strategy.")
    applied_actions: list[str] = Field(default_factory=list, description="Minimal patch actions that were applied.")
    verification: list[str] = Field(default_factory=list, description="Observed signals used to confirm whether the protection worked.")
    status: ExecutionStatus = Field(description="Protection phase result.")
    artifacts: list[ArtifactRef] = Field(default_factory=list, description="Artifacts created while applying or validating protection.")
    next_action: str = Field(description="Recommended next action after protection handling.")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM, description="Confidence in the protection assessment.")
