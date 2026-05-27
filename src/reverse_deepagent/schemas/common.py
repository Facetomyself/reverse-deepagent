from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SchemaBaseModel(BaseModel):
    """Shared strict base model for all public schemas."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ReverseMode(str, Enum):
    FULL_WORKFLOW = "full-workflow"
    PAGE_AUTOMATION = "page-automation"
    STEALTH_CONTEXT = "stealth-context"
    PARAMETER_WORKFLOW = "parameter-workflow"
    FIND_ENTRY = "find-entry"
    EXTRACT_LOGIC = "extract-logic"
    AST_DEOBFUSCATE = "ast-deobfuscate"
    RUNTIME_OBSERVE = "runtime-observe"
    DEBUG_BLOCKED = "debug-blocked"


class ReverseStage(str, Enum):
    ROUTE = "route"
    CONTEXT = "context"
    TRIAGE = "triage"
    PAGE_ACTION = "page-action"
    NETWORK = "network"
    RECON = "recon"
    SOURCE = "source"
    LOCATE_ENTRY = "locate-entry"
    BREAKPOINT = "breakpoint"
    HOOK = "hook"
    CONFIRM_ENTRY = "confirm-entry"
    RUNTIME_VERIFY = "runtime-verify"
    DEOBFUSCATE = "deobfuscate"
    LOGIC_EXTRACT = "logic-extract"
    SAMPLE_VERIFY = "sample-verify"
    REPLAY = "replay"
    DELIVERY = "delivery"
    REPLAY_DELIVERY = "replay-delivery"
    DETECTION_TRIAGE = "detection-triage"
    MINIMAL_PATCH = "minimal-patch"
    RETEST = "retest"
    HANDOFF = "handoff"
    PROTECTION = "protection"
    FINAL = "final"


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ArtifactKind(str, Enum):
    REPORT = "report"
    EXPORT = "export"
    SCREENSHOT = "screenshot"
    SESSION = "session"
    REBUILD = "rebuild"
    EVIDENCE = "evidence"
    LOG = "log"
    JSON = "json"
    MARKDOWN = "markdown"
    OTHER = "other"


class EvidenceKind(str, Enum):
    DYNAMIC = "dynamic"
    STATIC = "static"
    REQUEST = "request"
    CALLSTACK = "callstack"
    HOOK = "hook"
    WEBSOCKET = "websocket"
    STORAGE = "storage"
    SCREENSHOT = "screenshot"
    NOTE = "note"
    OTHER = "other"


class KeyFindings(SchemaBaseModel):
    """Structured findings split by certainty level."""

    facts: list[str] = Field(default_factory=list, description="Verified facts backed by evidence.")
    inferences: list[str] = Field(default_factory=list, description="Reasoned conclusions derived from evidence.")
    unknowns: list[str] = Field(default_factory=list, description="Open questions or gaps that remain unresolved.")


class EvidenceItem(SchemaBaseModel):
    """A single evidence record collected during reverse analysis."""

    summary: str = Field(description="Short human-readable summary of the evidence.")
    kind: EvidenceKind = Field(default=EvidenceKind.OTHER, description="Evidence category.")
    source: str | None = Field(default=None, description="Origin of the evidence, such as a tool, file, request, or script URL.")
    anchor: str | None = Field(default=None, description="Anchor reference like request id, script id, line number, or file path.")
    details: dict[str, Any] = Field(default_factory=dict, description="Machine-readable detail payload.")
    confidence: ConfidenceLevel | None = Field(default=None, description="Confidence for this individual evidence item.")


class ArtifactRef(SchemaBaseModel):
    """Reference to a generated artifact or persisted file."""

    path: str = Field(description="Virtual or filesystem path of the artifact.")
    kind: ArtifactKind = Field(default=ArtifactKind.OTHER, description="Artifact type.")
    description: str | None = Field(default=None, description="Short explanation of why the artifact matters.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata like mime type, stage, or export identifiers.")
