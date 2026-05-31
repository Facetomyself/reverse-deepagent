from __future__ import annotations

from typing import Any, Callable

from reverse_deepagent.runtime.base import WebReverseRuntime


BrowserTool = Callable[..., dict[str, Any]]


def make_ensure_browser_session_tool(runtime: WebReverseRuntime) -> BrowserTool:
    """Create a tool wrapper that exposes normalized browser session state."""

    def ensure_browser_session() -> dict[str, Any]:
        return runtime.ensure_browser_session().model_dump(mode="json")

    ensure_browser_session.__name__ = "ensure_browser_session"
    ensure_browser_session.__doc__ = "Ensure the browser session is reachable and return normalized session state."
    return ensure_browser_session


def make_browser_provider_matrix_tool(registry_factory=None) -> BrowserTool:
    """Create a side-effect-free BrowserProvider registry matrix tool."""

    from reverse_deepagent.browser import (
        BROWSER_PROVIDER_ENTRY_POINT_GROUP,
        build_default_browser_provider_registry,
    )
    from reverse_deepagent.browser.smoke import browser_provider_metadata_matrix_payload

    effective_registry_factory = registry_factory or build_default_browser_provider_registry

    def list_browser_providers() -> dict[str, Any]:
        registry = effective_registry_factory()
        provider_metadata = registry.list_registration_metadata()
        payload = browser_provider_metadata_matrix_payload(provider_metadata=provider_metadata)
        payload["entry_point_group"] = BROWSER_PROVIDER_ENTRY_POINT_GROUP
        payload["provider_registration_metadata"] = provider_metadata
        payload["registered_provider_ids"] = registry.provider_ids()
        payload["ok"] = all(bool(item.get("configured")) for item in payload["providers"])
        return payload

    list_browser_providers.__name__ = "list_browser_providers"
    list_browser_providers.__doc__ = (
        "List BrowserProvider registration metadata and capability matrix without launching browsers, "
        "probing CDP endpoints, invoking provider factories, or using MCP."
    )
    return list_browser_providers


def make_describe_browser_provider_tool(registry_factory=None) -> BrowserTool:
    """Create a side-effect-free single BrowserProvider metadata lookup tool."""

    from reverse_deepagent.browser import (
        BROWSER_PROVIDER_ENTRY_POINT_GROUP,
        BrowserProviderRegistryError,
        build_default_browser_provider_registry,
    )
    from reverse_deepagent.browser.smoke import CAPABILITY_FLAG_KEYS

    effective_registry_factory = registry_factory or build_default_browser_provider_registry

    def describe_browser_provider(provider_id: str = "playwright-chromium") -> dict[str, Any]:
        registry = effective_registry_factory()
        try:
            registration = registry.resolve(provider_id)
        except BrowserProviderRegistryError as exc:
            return {
                "ok": False,
                "provider_id": provider_id,
                "error": str(exc),
                "entry_point_group": BROWSER_PROVIDER_ENTRY_POINT_GROUP,
                "registered_provider_ids": registry.provider_ids(),
                "side_effect_policy": {
                    "metadata_only": True,
                    "provider_factory_invoked": False,
                    "browser_started": False,
                    "cdp_probed": False,
                    "mcp_used": False,
                },
            }
        capabilities = registration.capabilities.model_dump(mode="json")
        return {
            "ok": True,
            "provider_id": registration.provider_id,
            "requested_provider_id": provider_id,
            "aliases": list(registration.aliases),
            "keys": list(registration.keys),
            "entry_point_group": BROWSER_PROVIDER_ENTRY_POINT_GROUP,
            "capabilities": capabilities,
            "capability_matrix": {key: bool(capabilities.get(key)) for key in CAPABILITY_FLAG_KEYS},
            "side_effect_policy": {
                "metadata_only": True,
                "provider_factory_invoked": False,
                "browser_started": False,
                "cdp_probed": False,
                "mcp_used": False,
            },
        }

    describe_browser_provider.__name__ = "describe_browser_provider"
    describe_browser_provider.__doc__ = (
        "Describe one BrowserProvider by id or alias using registry metadata only; does not launch browsers or probe CDP."
    )
    return describe_browser_provider
