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
from .registry import BrowserProviderFactory, BrowserProviderRegistration, BrowserProviderRegistry, BrowserProviderRegistryError
from .session import PlaywrightBrowserPageAdapter, PlaywrightBrowserSessionAdapter, PlaywrightCDPSessionAdapter
from .smoke import (
    DEFAULT_BROWSER_PROVIDER_MATRIX,
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
    "browser_provider_smoke_matrix_payload",
    "browser_provider_smoke_row",
    "legacy_browser_provider_payload_from_smoke_row",
    "metadata_has_secret_like_keys",
]
