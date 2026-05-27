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


class ReverseRuntime(ABC):
    """Stable execution interface consumed by the agent layer.

    Implementations may use MCP, CLI, CDP, Playwright, or mobile tooling behind the scenes,
    but orchestration code should only depend on this interface.
    """

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
