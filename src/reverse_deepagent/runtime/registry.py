from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from typing import Any, Callable

from reverse_deepagent.runtime.base import ReverseRuntime, RuntimeBackendCapabilities
from reverse_deepagent.runtime.factories import (
    _android_adb_runtime_factory,
    _browser_cli_runtime_factory,
    _chrome_cdp_runtime_factory,
    _ios_simulator_runtime_factory,
    _mini_program_devtools_runtime_factory,
    _mock_runtime_factory,
    _native_web_runtime_factory,
    _playwright_cli_runtime_factory,
    _remote_cdp_provider_runtime_factory,
)
from reverse_deepagent.runtime.legacy_mcp import (
    LEGACY_MCP_BACKEND_ID,
    LegacyMcpPluginUnavailableError,
    is_legacy_mcp_runtime_kind,
    legacy_mcp_install_guidance,
    legacy_mcp_backend_registration,
)

RuntimeBackendFactory = Callable[..., ReverseRuntime]
RUNTIME_BACKEND_ENTRY_POINT_GROUP = "reverse_deepagent.runtime_backends"


@dataclass(frozen=True, slots=True)
class RuntimeBackendRegistration:
    """Factory registration for one runtime backend."""

    backend_id: str
    capabilities: RuntimeBackendCapabilities
    factory: RuntimeBackendFactory
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def keys(self) -> tuple[str, ...]:
        return (self.backend_id, *self.aliases)


class RuntimeBackendRegistry:
    """Small runtime backend registry used by coordinator / CLI entrypoints."""

    def __init__(self) -> None:
        self._registrations: dict[str, RuntimeBackendRegistration] = {}
        self._aliases: dict[str, str] = {}

    def register(self, registration: RuntimeBackendRegistration) -> None:
        canonical = registration.backend_id
        if registration.capabilities.backend_id != canonical:
            raise ValueError(
                "Runtime backend capability id mismatch: "
                f"registration={canonical!r}, capabilities={registration.capabilities.backend_id!r}"
            )
        for key in registration.keys:
            if key in self._registrations or key in self._aliases:
                raise ValueError(f"Runtime backend key already registered: {key}")
        self._registrations[canonical] = registration
        for alias in registration.aliases:
            self._aliases[alias] = canonical

    def load_entry_points(self, group: str = RUNTIME_BACKEND_ENTRY_POINT_GROUP) -> list[str]:
        """Load runtime backend registrations from Python package entry points.

        Entry-point plugins are the migration seam for moving optional backends
        such as legacy MCP out of the core package. Loading an entry point may
        import plugin Python code, but it must only return registration metadata
        and factories; factories are not invoked here, so listing metadata stays
        free of browser / MCP / device side effects.
        """

        loaded_backend_ids: list[str] = []
        for entry_point in sorted(_entry_points_for_group(group), key=lambda item: item.name):
            try:
                plugin_value = entry_point.load()
            except Exception as exc:
                raise RuntimeError(f"Failed to load runtime backend entry point {entry_point.name!r}: {exc}") from exc
            registrations = self._coerce_plugin_registrations(entry_point.name, plugin_value)
            for registration in registrations:
                self.register(registration)
                loaded_backend_ids.append(registration.backend_id)
        return loaded_backend_ids

    def resolve(self, backend_id: str) -> RuntimeBackendRegistration:
        canonical = backend_id if backend_id in self._registrations else self._aliases.get(backend_id)
        if canonical is None:
            known = ", ".join(self.backend_ids())
            raise ValueError(f"Unsupported runtime backend: {backend_id}. Known backends: {known}")
        return self._registrations[canonical]

    def is_registered(self, backend_id: str) -> bool:
        return backend_id in self._registrations or backend_id in self._aliases

    def create(self, backend_id: str, **kwargs: Any) -> ReverseRuntime:
        registration = self.resolve(backend_id)
        return registration.factory(**kwargs)

    def backend_ids(self) -> list[str]:
        return sorted([*self._registrations, *self._aliases])

    def list_capabilities(self) -> list[RuntimeBackendCapabilities]:
        return [self._registrations[key].capabilities for key in sorted(self._registrations)]

    def list_metadata(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.list_capabilities()]

    def list_registration_metadata(self) -> list[dict[str, Any]]:
        """Return canonical backend metadata plus aliases without creating runtimes."""

        payloads: list[dict[str, Any]] = []
        for backend_id in sorted(self._registrations):
            registration = self._registrations[backend_id]
            payload = registration.capabilities.model_dump(mode="json")
            payload["aliases"] = list(registration.aliases)
            payload["keys"] = list(registration.keys)
            payloads.append(payload)
        return payloads

    @staticmethod
    def _coerce_plugin_registrations(entry_point_name: str, value: Any) -> list[RuntimeBackendRegistration]:
        if isinstance(value, RuntimeBackendRegistration):
            return [value]
        if callable(value):
            return RuntimeBackendRegistry._coerce_plugin_registrations(entry_point_name, value())
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, dict)):
            registrations = list(value)
            if all(isinstance(item, RuntimeBackendRegistration) for item in registrations):
                return registrations
        raise TypeError(
            "Runtime backend entry point "
            f"{entry_point_name!r} must return a RuntimeBackendRegistration, "
            "a callable producing registrations, or an iterable of registrations."
        )


def _entry_points_for_group(group: str) -> list[Any]:
    entry_points = importlib_metadata.entry_points()
    if hasattr(entry_points, "select"):
        selected = entry_points.select(group=group)
    else:  # pragma: no cover - compatibility with older importlib.metadata APIs
        selected = entry_points.get(group, [])
    return list(selected)


def build_default_runtime_registry(*, include_entry_points: bool = True, include_legacy_mcp: bool = True) -> RuntimeBackendRegistry:
    """Build the default runtime backend registry without starting external processes."""

    registry = RuntimeBackendRegistry()
    registry.register(
        RuntimeBackendRegistration(
            backend_id="mock",
            aliases=("in-process",),
            factory=_mock_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="mock",
                display_name="Mock JSReverser Runtime",
                transport="in-process",
                target_platforms=["web"],
                supports_browser_session=True,
                supports_web_recon=True,
                supports_protection_patch=True,
                supports_artifact_export=True,
                supports_runtime_context=True,
                supports_replay_validation=True,
                evidence_kinds=["request", "callstack", "static", "dynamic", "storage", "note"],
                artifact_kinds=["json", "export", "rebuild", "markdown"],
                notes=["deterministic in-process backend for tests and public CI"],
            ),
        )
    )
    registry.register(
        RuntimeBackendRegistration(
            backend_id="native-web",
            aliases=("web", "browser-native"),
            factory=_native_web_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="native-web",
                display_name="Native Web Runtime",
                transport="browser-provider",
                target_platforms=["web"],
                supports_browser_session=True,
                supports_web_recon=True,
                supports_protection_patch=True,
                supports_artifact_export=True,
                supports_runtime_context=True,
                supports_replay_validation=True,
                managed_chrome=False,
                mcp_backed=False,
                evidence_kinds=["request", "static", "dynamic", "storage", "screenshot", "note"],
                artifact_kinds=["json", "markdown", "screenshot"],
                notes=[
                    "native BrowserProvider-backed Web runtime",
                    "does not require jsreverser-mcp",
                    "default provider is playwright-chromium",
                ],
                config={"default_browser_provider": "playwright-chromium"},
            ),
        )
    )

    registry.register(
        RuntimeBackendRegistration(
            backend_id="remote-cdp",
            aliases=("cdp-provider", "chrome-cdp-provider"),
            factory=_remote_cdp_provider_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="remote-cdp",
                display_name="Remote Chrome CDP BrowserProvider",
                transport="remote-cdp",
                target_platforms=["web"],
                supports_browser_session=True,
                supports_web_recon=True,
                supports_protection_patch=True,
                supports_artifact_export=True,
                supports_runtime_context=True,
                supports_replay_validation=True,
                managed_chrome=False,
                mcp_backed=False,
                evidence_kinds=["request", "static", "dynamic", "storage", "screenshot", "note"],
                artifact_kinds=["json", "markdown", "screenshot"],
                notes=[
                    "connects to an already-running Chrome DevTools endpoint",
                    "useful as a smoke path when Playwright is unavailable",
                ],
                config={"default_browser_url": "http://127.0.0.1:9222"},
            ),
        )
    )

    registry.register(
        RuntimeBackendRegistration(
            backend_id="playwright-cli",
            aliases=("playwright", "pw-cli"),
            factory=_playwright_cli_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="playwright-cli",
                display_name="Playwright CLI Runtime",
                transport="playwright-cli",
                target_platforms=["web"],
                supports_browser_session=True,
                supports_web_recon=True,
                supports_protection_patch=False,
                supports_artifact_export=True,
                supports_runtime_context=False,
                supports_replay_validation=False,
                managed_chrome=False,
                mcp_backed=False,
                evidence_kinds=["static", "dynamic", "note"],
                artifact_kinds=["json", "export", "source"],
                notes=[
                    "lightweight Web backend using side-effect-light Playwright CLI probes",
                    "does not launch browsers or capture live network traffic",
                ],
                config={"default_command": "playwright --version"},
            ),
        )
    )
    registry.register(
        RuntimeBackendRegistration(
            backend_id="chrome-cdp",
            aliases=("cdp", "devtools"),
            factory=_chrome_cdp_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="chrome-cdp",
                display_name="Chrome CDP Runtime",
                transport="chrome-cdp",
                target_platforms=["web"],
                supports_browser_session=True,
                supports_web_recon=True,
                supports_protection_patch=False,
                supports_artifact_export=True,
                supports_runtime_context=False,
                supports_replay_validation=False,
                managed_chrome=False,
                mcp_backed=False,
                evidence_kinds=["static", "dynamic", "note"],
                artifact_kinds=["json", "export", "source", "session"],
                notes=[
                    "lightweight Web backend that probes an existing Chrome DevTools endpoint",
                    "never starts Chrome; use managed Chrome launcher explicitly if needed",
                ],
                config={"default_browser_url": "http://127.0.0.1:9222"},
            ),
        )
    )
    registry.register(
        RuntimeBackendRegistration(
            backend_id="browser-cli",
            aliases=("cli-browser", "browser-command"),
            factory=_browser_cli_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="browser-cli",
                display_name="Generic Browser CLI Runtime",
                transport="browser-cli",
                target_platforms=["web"],
                supports_browser_session=True,
                supports_web_recon=True,
                supports_protection_patch=False,
                supports_artifact_export=True,
                supports_runtime_context=False,
                supports_replay_validation=False,
                managed_chrome=False,
                mcp_backed=False,
                evidence_kinds=["static", "dynamic", "note"],
                artifact_kinds=["json", "export", "source"],
                notes=[
                    "generic command-probed Web backend for portable CLI shims",
                    "command is not configured by default and must be passed explicitly for a healthy session",
                ],
                config={"default_command": None},
            ),
        )
    )

    registry.register(
        RuntimeBackendRegistration(
            backend_id="android-adb",
            aliases=("adb", "android-device"),
            factory=_android_adb_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="android-adb",
                display_name="Android ADB Runtime",
                transport="adb",
                target_platforms=["android"],
                supports_browser_session=False,
                supports_web_recon=False,
                supports_protection_patch=True,
                supports_artifact_export=True,
                supports_runtime_context=True,
                supports_replay_validation=False,
                evidence_kinds=["static", "dynamic", "storage", "network", "note"],
                artifact_kinds=["json", "export", "runtime-context", "trace", "static-analysis"],
                notes=["requires local adb for explicit probes; registry listing is side-effect free"],
                config={"default_command": "adb", "requires_device": True},
            ),
        )
    )
    registry.register(
        RuntimeBackendRegistration(
            backend_id="ios-simulator",
            aliases=("simctl", "ios-sim"),
            factory=_ios_simulator_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="ios-simulator",
                display_name="iOS Simulator Runtime",
                transport="xcrun-simctl",
                target_platforms=["ios"],
                supports_browser_session=False,
                supports_web_recon=False,
                supports_protection_patch=True,
                supports_artifact_export=True,
                supports_runtime_context=True,
                supports_replay_validation=False,
                evidence_kinds=["static", "dynamic", "storage", "network", "note"],
                artifact_kinds=["json", "export", "runtime-context", "trace", "static-analysis"],
                notes=["requires local xcrun/simctl for explicit probes; registry listing is side-effect free"],
                config={"default_command": "xcrun simctl", "requires_simulator": True},
            ),
        )
    )
    registry.register(
        RuntimeBackendRegistration(
            backend_id="mini-program-devtools",
            aliases=("mp-devtools", "wechat-devtools"),
            factory=_mini_program_devtools_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="mini-program-devtools",
                display_name="Mini-program Developer Tools Runtime",
                transport="vendor-devtools-cli",
                target_platforms=["mini-program"],
                supports_browser_session=False,
                supports_web_recon=False,
                supports_protection_patch=True,
                supports_artifact_export=True,
                supports_runtime_context=True,
                supports_replay_validation=False,
                evidence_kinds=["static", "dynamic", "hook", "storage", "network", "note"],
                artifact_kinds=["json", "export", "runtime-context", "trace", "static-analysis", "package-metadata"],
                notes=["requires configured vendor devtools CLI for explicit probes; registry listing is side-effect free"],
                config={"vendor": "wechat", "requires_gui_tool": "depends-on-vendor"},
            ),
        )
    )
    if include_entry_points:
        registry.load_entry_points()
    if include_legacy_mcp and not registry.is_registered(LEGACY_MCP_BACKEND_ID):
        try:
            registry.register(legacy_mcp_backend_registration())
        except LegacyMcpPluginUnavailableError:
            # Core no longer ships a built-in legacy MCP fallback. The optional
            # plugin is loaded through entry points when installed; otherwise
            # runtime construction will surface structured install guidance.
            pass
    return registry


DEFAULT_RUNTIME_BACKEND_REGISTRY = build_default_runtime_registry()


def list_runtime_backends() -> list[dict[str, Any]]:
    """Return JSON-serializable metadata for known runtime backends."""

    return DEFAULT_RUNTIME_BACKEND_REGISTRY.list_metadata()


def build_runtime(
    runtime_kind: str,
    browser_url: str | None = None,
    mcp_command: str | None = None,
    **runtime_kwargs: Any,
) -> ReverseRuntime:
    """Build a runtime backend by id or alias."""

    try:
        return DEFAULT_RUNTIME_BACKEND_REGISTRY.create(
            runtime_kind,
            browser_url=browser_url,
            mcp_command=mcp_command,
            **runtime_kwargs,
        )
    except ValueError as exc:
        if is_legacy_mcp_runtime_kind(runtime_kind) and not DEFAULT_RUNTIME_BACKEND_REGISTRY.is_registered(runtime_kind):
            guidance = legacy_mcp_install_guidance()
            raise LegacyMcpPluginUnavailableError(
                "Legacy MCP optional backend is not installed. "
                f"runtime={runtime_kind!r}; package={guidance['package']!r}; "
                f"install_hint={guidance['install_hint']!r}; "
                f"preferred_web_runtime={guidance['preferred_web_runtime']!r}."
            ) from exc
        raise
