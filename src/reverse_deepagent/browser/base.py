from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.schemas.common import SchemaBaseModel


class BrowserProviderError(RuntimeError):
    """Base error for browser provider lifecycle failures."""


class BrowserProviderUnavailableError(BrowserProviderError):
    """Raised when a provider dependency, binary, or endpoint is unavailable."""


class BrowserPageRef(SchemaBaseModel):
    """Serializable reference to one browser page/tab."""

    page_id: str = Field(description="Provider-scoped page identifier.")
    url: str | None = Field(default=None, description="Current page URL when available.")
    title: str | None = Field(default=None, description="Current page title when available.")
    selected: bool = Field(default=False, description="Whether this page is the provider-selected active page.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Non-secret provider-specific metadata.")


@runtime_checkable
class BrowserCDPSession(Protocol):
    """Minimal CDP session shape used by future collectors."""

    def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        ...


@runtime_checkable
class BrowserPage(Protocol):
    """Provider-neutral page operations consumed by native collectors."""

    @property
    def url(self) -> str:
        ...

    def goto(self, url: str, timeout: float | None = None) -> None:
        ...

    def title(self) -> str:
        ...

    def content(self) -> str:
        ...

    def evaluate(self, expression: str) -> Any:
        ...

    def screenshot(self, path: str | None = None) -> bytes | None:
        ...

    def cdp_session(self) -> BrowserCDPSession | None:
        ...


@runtime_checkable
class BrowserSession(Protocol):
    """Provider-neutral browser session operations."""

    @property
    def provider_id(self) -> str:
        ...

    def list_pages(self) -> list[BrowserPageRef]:
        ...

    def new_page(self, url: str | None = None) -> BrowserPage:
        ...

    def get_active_page(self) -> BrowserPage | None:
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class BrowserProvider(Protocol):
    """Lifecycle boundary for replaceable browser implementations."""

    def describe(self) -> BrowserProviderCapabilities:
        ...

    def start(self) -> BrowserSession:
        ...

    def connect(self) -> BrowserSession:
        ...

    def stop(self) -> None:
        ...

    def is_available(self) -> bool:
        ...
