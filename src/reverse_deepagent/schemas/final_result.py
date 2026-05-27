from __future__ import annotations

from pydantic import Field

from .common import (
    ArtifactRef,
    ConfidenceLevel,
    EvidenceItem,
    ExecutionStatus,
    KeyFindings,
    ReverseMode,
    ReverseStage,
    SchemaBaseModel,
)
from .task_card import TaskCard


class FinalResult(SchemaBaseModel):
    """Top-level result returned to the user and downstream automation."""

    task_card: TaskCard = Field(description="Normalized task card for the reverse task.")
    mode: ReverseMode = Field(description="Selected reverse mode.")
    stage: ReverseStage = Field(description="Latest completed or current stage.")
    status: ExecutionStatus = Field(description="Overall task outcome.")
    key_findings: KeyFindings = Field(default_factory=KeyFindings, description="Top-level findings split into facts, inferences, and unknowns.")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="Evidence promoted to the final result.")
    artifacts: list[ArtifactRef] = Field(default_factory=list, description="Artifacts that support the final result.")
    next_action: str = Field(description="Explicit next step for continuing the task.")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM, description="Overall confidence in the final result.")
