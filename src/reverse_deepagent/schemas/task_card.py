from __future__ import annotations

from pydantic import Field

from .common import SchemaBaseModel


class TaskCard(SchemaBaseModel):
    """Normalized reverse-engineering task card."""

    target_url_or_file: str = Field(description="Target page URL, script path, file path, HAR, bundle, or wasm target.")
    target_param_or_api: str = Field(description="Target parameter, token, cookie, sign, or API of interest.")
    goal: str = Field(description="Primary goal, such as finding an entry point, reconstructing logic, or replaying a request.")
    boundaries: str = Field(description="Operational constraints, such as login rules, rate limits, and no-touch boundaries.")
    sample_request: str | None = Field(default=None, description="Optional sample request or endpoint clue.")
    protection_hints: list[str] = Field(default_factory=list, description="Optional hints like debugger, webpack, wasm, websocket, or console.clear.")
