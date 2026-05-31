from .base import (
    BrowserCDPSession,
    BrowserPage,
    BrowserPageRef,
    BrowserProvider,
    BrowserProviderError,
    BrowserProviderUnavailableError,
    BrowserSession,
)
from .capabilities import BrowserProviderCapabilities, metadata_has_secret_like_keys
from .registry import (
    BROWSER_PROVIDER_ENTRY_POINT_GROUP,
    BrowserProviderFactory,
    BrowserProviderRegistration,
    BrowserProviderRegistry,
    BrowserProviderRegistryError,
    build_default_browser_provider_registry,
    cloakbrowser_browser_provider_registration,
    playwright_chromium_browser_provider_registration,
    remote_cdp_browser_provider_registration,
)
from .session import PlaywrightBrowserPageAdapter, PlaywrightBrowserSessionAdapter, PlaywrightCDPSessionAdapter
from .smoke import (
    DEFAULT_BROWSER_PROVIDER_MATRIX,
    browser_provider_metadata_matrix_payload,
    browser_provider_smoke_matrix_payload,
    browser_provider_smoke_row,
    legacy_browser_provider_payload_from_smoke_row,
)

__all__ = [
    "BrowserCDPSession",
    "BrowserPage",
    "BrowserPageRef",
    "BrowserProvider",
    "BrowserProviderCapabilities",
    "BrowserProviderError",
    "BROWSER_PROVIDER_ENTRY_POINT_GROUP",
    "BrowserProviderFactory",
    "BrowserProviderRegistration",
    "BrowserProviderRegistry",
    "BrowserProviderRegistryError",
    "BrowserProviderUnavailableError",
    "DEFAULT_BROWSER_PROVIDER_MATRIX",
    "BrowserSession",
    "PlaywrightBrowserPageAdapter",
    "PlaywrightBrowserSessionAdapter",
    "PlaywrightCDPSessionAdapter",
    "build_default_browser_provider_registry",
    "browser_provider_metadata_matrix_payload",
    "browser_provider_smoke_matrix_payload",
    "browser_provider_smoke_row",
    "cloakbrowser_browser_provider_registration",
    "legacy_browser_provider_payload_from_smoke_row",
    "playwright_chromium_browser_provider_registration",
    "remote_cdp_browser_provider_registration",
    "metadata_has_secret_like_keys",
]
