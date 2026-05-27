from __future__ import annotations

from pydantic import Field

from .common import ConfidenceLevel, ReverseMode, ReverseStage, SchemaBaseModel


class RouterResult(SchemaBaseModel):
    """Route decision produced by the router subagent."""

    selected_mode: ReverseMode = Field(description="Chosen top-level mode for the task.")
    selected_playbook: str = Field(description="Path or identifier of the selected playbook.")
    initial_stage: ReverseStage = Field(description="First execution stage after routing.")
    reasoning: list[str] = Field(default_factory=list, description="Concise reasons that justify the route decision.")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM, description="Confidence in the route decision.")
    next_action: str = Field(description="Immediate next action after routing.")
