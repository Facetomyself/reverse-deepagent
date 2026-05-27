from __future__ import annotations

from pydantic import Field

from .common import (
    ArtifactRef,
    ConfidenceLevel,
    EvidenceItem,
    ExecutionStatus,
    KeyFindings,
    ReverseStage,
    SchemaBaseModel,
)


class ReconResult(SchemaBaseModel):
    """Structured result returned by the Web Recon subagent."""

    status: ExecutionStatus = Field(description="Execution status for the recon phase.")
    stage: ReverseStage = Field(default=ReverseStage.RECON, description="Current stage, normally recon for this result type.")
    key_findings: KeyFindings = Field(default_factory=KeyFindings, description="Structured findings from recon.")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="Evidence gathered during recon.")
    artifacts: list[ArtifactRef] = Field(default_factory=list, description="Artifacts generated during recon.")
    next_action: str = Field(description="Recommended immediate next action.")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM, description="Confidence in the recon conclusion.")
