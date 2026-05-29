from __future__ import annotations

from typing import Any

from pydantic import Field

from reverse_deepagent.schemas.common import SchemaBaseModel


class BrowserProviderCapabilities(SchemaBaseModel):
    """Serializable, non-secret capability metadata for a browser provider."""

    provider_id: str = Field(description="Stable browser provider id, such as playwright-chromium or cloakbrowser.")
    display_name: str = Field(description="Human-readable provider name.")
    engine: str = Field(default="unknown", description="Browser engine or family, for example chromium or webkit.")
    transport: str = Field(default="unknown", description="Provider transport, for example playwright, cdp, or remote-cdp.")
    target_platforms: list[str] = Field(default_factory=lambda: ["web"], description="Target platforms supported by the provider.")
    supports_launch: bool = Field(default=False, description="Whether the provider can launch a browser process/context.")
    supports_connect: bool = Field(default=False, description="Whether the provider can connect to an already-running browser.")
    supports_persistent_context: bool = Field(default=False, description="Whether the provider supports durable profile/login-state contexts.")
    supports_cdp: bool = Field(default=False, description="Whether the provider exposes Chrome DevTools Protocol sessions.")
    supports_playwright_api: bool = Field(default=False, description="Whether the provider exposes a Playwright-compatible page/session API.")
    supports_proxy: bool = Field(default=False, description="Whether provider-level proxy configuration is supported.")
    supports_stealth: bool = Field(default=False, description="Whether the provider includes stealth/fingerprint hardening.")
    supports_humanize: bool = Field(default=False, description="Whether the provider supports humanized click/type/scroll behavior.")
    supports_extensions: bool = Field(default=False, description="Whether browser extensions can be loaded.")
    supports_mobile_emulation: bool = Field(default=False, description="Whether mobile viewport/device emulation is supported.")
    supports_network_events: bool = Field(default=False, description="Whether request/response event collection is supported.")
    supports_response_body: bool = Field(default=False, description="Whether response body capture is supported.")
    supports_request_initiator: bool = Field(default=False, description="Whether request initiator/callstack data can be captured.")
    supports_script_source: bool = Field(default=False, description="Whether loaded script source can be inventoried or fetched.")
    supports_websocket_frames: bool = Field(default=False, description="Whether WebSocket frame data can be captured.")
    supports_breakpoints: bool = Field(default=False, description="Whether debugger breakpoints/callframe operations are supported.")
    supports_runtime_eval: bool = Field(default=False, description="Whether in-page JavaScript evaluation is supported.")
    managed_browser: bool = Field(default=False, description="Whether the provider manages browser lifecycle itself.")
    notes: list[str] = Field(default_factory=list, description="Operational notes and known limitations.")
    config: dict[str, Any] = Field(default_factory=dict, description="Non-secret default/config summary.")


BROWSER_PROVIDER_SECRET_KEYWORDS = (
    "key",
    "token",
    "secret",
    "password",
    "cookie",
    "authorization",
    "credential",
)


def metadata_has_secret_like_keys(value: Any) -> bool:
    """Return True if a JSON-like metadata object contains obviously secret key names."""

    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(keyword in lowered for keyword in BROWSER_PROVIDER_SECRET_KEYWORDS):
                return True
            if metadata_has_secret_like_keys(item):
                return True
        return False
    if isinstance(value, list):
        return any(metadata_has_secret_like_keys(item) for item in value)
    return False
