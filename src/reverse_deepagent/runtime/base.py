from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import Field

from reverse_deepagent.schemas.common import SchemaBaseModel
from reverse_deepagent.schemas.final_result import FinalResult
from reverse_deepagent.schemas.protection_result import ProtectionResult
from reverse_deepagent.schemas.recon_result import ReconResult
from reverse_deepagent.schemas.router_result import RouterResult
from reverse_deepagent.schemas.task_card import TaskCard


class BrowserSessionInfo(SchemaBaseModel):
    """Normalized browser runtime state used by the orchestration layer."""

    healthy: bool = Field(description="Whether the browser runtime is reachable and ready.")
    page_count: int = Field(default=0, description="Number of pages currently visible to the runtime.")
    selected_page_idx: int | None = Field(default=None, description="Best-effort selected page index.")
    active_url: str | None = Field(default=None, description="Current or selected page URL.")
    details: dict[str, Any] = Field(default_factory=dict, description="Raw normalized details returned by the runtime.")


class RuntimeExportBundle(SchemaBaseModel):
    """Structured export payload returned by the runtime layer."""

    final_result: FinalResult | None = Field(default=None, description="Optional final result snapshot associated with the export.")
    exports: list[dict[str, Any]] = Field(default_factory=list, description="Raw export payloads returned by the runtime.")
    artifacts: list[dict[str, Any]] = Field(default_factory=list, description="Normalized artifact references represented as plain dictionaries.")


class RuntimeBackendCapabilities(SchemaBaseModel):
    """Serializable capability metadata for a runtime backend."""

    backend_id: str = Field(description="Stable backend identifier, such as mock or jsreverser-mcp.")
    display_name: str = Field(description="Human-readable backend name.")
    transport: str = Field(default="unknown", description="Implementation transport, such as in-process or mcp-stdio.")
    target_platforms: list[str] = Field(default_factory=list, description="Supported target platforms, for example web, android, ios, or mini-program.")
    supports_browser_session: bool = Field(default=False, description="Whether the backend can inspect or manage a browser session.")
    supports_web_recon: bool = Field(default=False, description="Whether the backend can run Web recon.")
    supports_protection_patch: bool = Field(default=False, description="Whether the backend can apply minimal anti-debug / protection patches.")
    supports_artifact_export: bool = Field(default=False, description="Whether the backend can export runtime/session artifacts.")
    supports_runtime_context: bool = Field(default=False, description="Whether the backend can capture storage / environment context.")
    supports_replay_validation: bool = Field(default=False, description="Whether the backend can validate candidate functions at runtime.")
    managed_chrome: bool = Field(default=False, description="Whether callers can pair the backend with the managed Chrome launcher.")
    mcp_backed: bool = Field(default=False, description="Whether the backend is backed by an MCP transport.")
    evidence_kinds: list[str] = Field(default_factory=list, description="Evidence categories the backend commonly emits.")
    artifact_kinds: list[str] = Field(default_factory=list, description="Artifact categories the backend commonly emits.")
    notes: list[str] = Field(default_factory=list, description="Operational notes or limitations.")
    config: dict[str, Any] = Field(default_factory=dict, description="Non-secret config summary useful for debugging.")


class RuntimeArtifactManifestEntry(SchemaBaseModel):
    """Typed manifest entry for one artifact produced by a runtime pipeline."""

    artifact_key: str = Field(description="Stable key used by artifact indexes, such as workspace_task_card.")
    path: str = Field(description="Filesystem or virtual artifact path.")
    category: str = Field(default="other", description="High-level category such as workspace, report, export, or rebuild.")
    kind: str = Field(default="other", description="Artifact kind such as json, markdown, rebuild, or export.")
    producer_backend_id: str = Field(description="Runtime backend that produced or orchestrated the artifact.")
    producer_transport: str = Field(default="unknown", description="Runtime transport used by the producer backend.")
    target_platforms: list[str] = Field(default_factory=list, description="Target platforms associated with the producer backend.")
    description: str | None = Field(default=None, description="Human-readable artifact description.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional machine-readable artifact metadata.")


class RuntimeArtifactManifest(SchemaBaseModel):
    """Typed manifest for artifacts emitted by a runtime pipeline run."""

    producer_backend_id: str = Field(description="Runtime backend that produced or orchestrated this manifest.")
    producer_transport: str = Field(default="unknown", description="Runtime transport used by the producer backend.")
    target_platforms: list[str] = Field(default_factory=list, description="Target platforms associated with this run.")
    entries: list[RuntimeArtifactManifestEntry] = Field(default_factory=list, description="Artifact entries in stable key order.")


class ReverseRuntime(ABC):
    """Stable execution interface consumed by the agent layer.

    Implementations may use MCP, CLI, CDP, Playwright, or mobile tooling behind the scenes,
    but orchestration code should only depend on this interface.
    """

    def describe_capabilities(self) -> RuntimeBackendCapabilities:
        """Return conservative capability metadata for this runtime backend."""

        return RuntimeBackendCapabilities(
            backend_id=self.__class__.__name__,
            display_name=self.__class__.__name__,
            notes=["backend did not override capability metadata"],
        )

    @abstractmethod
    def ensure_browser_session(self) -> BrowserSessionInfo:
        """Ensure the runtime browser session is reachable and ready."""

    @abstractmethod
    def run_web_recon(self, task_card: TaskCard, route_result: RouterResult) -> ReconResult:
        """Run the minimal Web recon flow and return a structured recon result."""

    @abstractmethod
    def apply_minimal_protection(self, protection_name: str, context: dict[str, Any] | None = None) -> ProtectionResult:
        """Apply the minimal protection patch for a blocked scenario."""

    @abstractmethod
    def export_reverse_artifacts(self, final_result: FinalResult | None = None) -> RuntimeExportBundle:
        """Export runtime artifacts such as reports, sessions, or rebuild bundles."""
