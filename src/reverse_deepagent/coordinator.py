from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from pydantic import Field

from reverse_deepagent.adapters.platforms import AndroidAdbRuntime, IosSimulatorRuntime, MiniProgramDevtoolsRuntime
from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.adapters.lightweight_web import LightweightWebRuntimeConfig, create_lightweight_web_runtime
from reverse_deepagent.adapters.native_web import create_native_web_runtime
from reverse_deepagent.evidence import promote_evidence, promotion_workspace_payloads
from reverse_deepagent.rebuild import write_rebuild_bundle
from reverse_deepagent.review_gate import evaluate_review_gate, review_gate_workspace_payload
from reverse_deepagent.runtime import (
    RuntimeBackendCapabilities,
    RuntimeBackendRegistration,
    RuntimeBackendRegistry,
    RuntimeExportBundle,
    ReverseRuntime,
    WebReverseRuntime,
)
from reverse_deepagent.runtime import RuntimeArtifactManifest, RuntimeArtifactManifestEntry
from reverse_deepagent.runtime.chrome import ChromeCommandResult, ChromeDebugConfig, ensure_chrome_debug, stop_chrome_debug
from reverse_deepagent.runtime.legacy_mcp import (
    LEGACY_MCP_BACKEND_ID,
    LegacyMcpPluginUnavailableError,
    is_legacy_mcp_runtime_kind,
    legacy_mcp_install_guidance,
    legacy_mcp_alias_warning as _legacy_mcp_alias_warning,
    legacy_mcp_backend_registration,
)
from reverse_deepagent.schemas import (
    ArtifactKind,
    ArtifactRef,
    ConfidenceLevel,
    EvidenceItem,
    EvidenceKind,
    ExecutionStatus,
    FinalResult,
    KeyFindings,
    ReconResult,
    ReverseStage,
    RouterResult,
    SchemaBaseModel,
    TaskCard,
)
from reverse_deepagent.tools.route_tools import normalize_task_card, route_from_task_card
from reverse_deepagent.workspace_contract import WorkspacePathResolver, workspace_contract_payload, workspace_manifest_alias_metadata

class ReversePipelineOutput(SchemaBaseModel):
    """Complete result returned by the deterministic coordinator pipeline."""

    final_result: FinalResult = Field(description="Final structured reverse result.")
    artifacts: dict[str, str] = Field(default_factory=dict, description="Generated artifact path index.")
    chrome_launch: ChromeCommandResult | None = Field(default=None, description="Chrome launch command result, if used.")
    chrome_stop: ChromeCommandResult | None = Field(default=None, description="Chrome stop command result, if used.")


class PlatformPipelineOutput(SchemaBaseModel):
    """Platform-neutral pipeline result for any ReverseRuntime backend."""

    final_result: FinalResult = Field(description="Final structured platform-neutral result.")
    artifacts: dict[str, str] = Field(default_factory=dict, description="Generated artifact path index.")
    runtime_capabilities: RuntimeBackendCapabilities = Field(description="Runtime backend capability snapshot used for routing.")
    runtime_export_bundle: RuntimeExportBundle = Field(description="Raw runtime export bundle emitted by the backend.")


class MockJSReverserBridge:
    """Deterministic JSReverser bridge for local demo and contract validation.

    The mock backend is intentionally profile-aware for localhost fixture URLs:
    it reads the fixture ``/app.js`` source, exposes matching network/source
    evidence, and returns validation samples that agree with the selected
    fixture profile. Non-fixture demo runs keep the historical static example.
    """

    def __init__(self, active_url: str = "https://example.com/search") -> None:
        self.active_url = active_url
        self._source_cache: dict[str, str] = {}
        self._health_cache: dict[str, Any] = {}

    def invoke(self, tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name == "check_browser_health":
            return {"status": "ok", "connected": True}
        if tool_name == "list_pages":
            return {"pages": [{"pageIdx": 0, "url": self.active_url, "selected": True}]}
        if tool_name == "new_page":
            self.active_url = str(params.get("url") or self.active_url)
            return {"ok": True, "created": True, "url": self.active_url}
        if tool_name == "navigate_page":
            self.active_url = str(params.get("url") or self.active_url)
            return {"ok": True, "navigated": True, "url": self.active_url}
        if tool_name == "network_request":
            return {"requests": self._network_requests()}
        if tool_name == "search_in_sources":
            return {"results": [self._source_hit(params.get("query", "sign"))]}
        if tool_name == "evaluate_script" and "__REVERSE_AGENT_VALIDATE_CANDIDATE__" in str(params.get("function", "")):
            return {"ok": True, "result": self._validation_result()}
        if tool_name == "evaluate_script":
            function_source = str(params.get("function", ""))
            if "dumpStorage" in function_source or "navigator" in function_source:
                return {"ok": True, "result": self._runtime_environment()}
            return {"ok": True, "result": {"readyState": "complete", "url": self.active_url}}
        if tool_name == "get_storage":
            return self._storage_payload()
        if tool_name == "get_request_initiator":
            return {
                "requestId": params.get("requestId"),
                "initiator": "window.reverseFixture.search -> fetch('/api/search')",
                "stack": ["search", "fetch"],
            }
        if tool_name == "get_script_source":
            return {
                "scriptId": params.get("scriptId"),
                "startLine": params.get("startLine"),
                "endLine": params.get("endLine"),
                "source": self._source_text(),
            }
        if tool_name == "inject_preload_script":
            return {"ok": True}
        if tool_name == "export_session_report":
            return {"ok": True, "format": params.get("format", "json"), "items": 3, "active_url": self.active_url}
        raise RuntimeError(f"Unsupported mock tool: {tool_name}")

    def _network_requests(self) -> list[dict[str, Any]]:
        if self._is_fixture_url():
            requests = [
                {"id": 101, "url": urljoin(self.active_url.rstrip("/") + "/", "api/search"), "method": "POST"},
                {"id": 102, "url": urljoin(self.active_url.rstrip("/") + "/", "app.js"), "method": "GET"},
            ]
            if self._profile() == "token-chain":
                requests.insert(0, {"id": 100, "url": urljoin(self.active_url.rstrip("/") + "/", "api/bootstrap"), "method": "GET"})
            return requests
        return [
            {"id": 101, "url": "https://example.com/api/search", "method": "POST"},
            {"id": 102, "url": "https://example.com/api/bootstrap", "method": "GET"},
        ]

    def _source_hit(self, query: Any) -> dict[str, Any]:
        source = self._source_text()
        line_number = self._build_sign_line_number(source)
        preview = self._line_at(source, line_number) or f"const token = build('{query}')"
        return {
            "scriptId": "fixture-app" if self._is_fixture_url() else "1",
            "url": urljoin(self.active_url.rstrip("/") + "/", "app.js") if self._is_fixture_url() else "https://example.com/static/app.js",
            "lineNumber": line_number,
            "preview": preview,
        }

    def _validation_result(self) -> dict[str, Any]:
        sign = self._sample_sign()
        return {
            "marker": "__REVERSE_AGENT_VALIDATE_CANDIDATE__",
            "function_name": "buildSign",
            "located": True,
            "callable_path": "window.reverseFixture.buildSign",
            "invocation_ok": True,
            "invocation_result_type": "string",
            "sign": sign,
            "sign_shape_ok": bool(sign),
            "replay_result": {
                "attempted": True,
                "ok": bool(sign),
                "status": 200,
                "echoed_sign": sign,
                "body": {"headers": {"x-sign": sign, "x-fixture-profile": self._profile()}},
            },
            "runtime_url": self.active_url,
        }

    def _source_text(self) -> str:
        if not self._is_fixture_url():
            return "function buildSign(keyword, timestamp) {\n  return `sig_${keyword}_${timestamp}`;\n}"
        app_js_url = urljoin(self.active_url.rstrip("/") + "/", "app.js")
        if app_js_url not in self._source_cache:
            self._source_cache[app_js_url] = self._fetch_text(app_js_url)
        return self._source_cache[app_js_url]

    def _health(self) -> dict[str, Any]:
        if not self._is_fixture_url():
            return {}
        health_url = urljoin(self.active_url.rstrip("/") + "/", "healthz")
        if health_url not in self._health_cache:
            try:
                self._health_cache[health_url] = json.loads(self._fetch_text(health_url))
            except Exception:
                self._health_cache[health_url] = {}
        return self._health_cache[health_url] if isinstance(self._health_cache[health_url], dict) else {}

    def _profile(self) -> str:
        return str(self._health().get("profile") or "default")

    def _sample_sign(self) -> str:
        keyword = "sign"
        timestamp = 1700000000000
        profile = self._profile()
        if not self._is_fixture_url():
            return f"sig_{keyword}_{timestamp}"
        raw = f"{keyword}:{timestamp}"
        if profile == "default":
            seeded = f"{raw}:reverse-agent-fixture"
            digest = sum(ord(char) for char in seeded) % 100000
            return f"sig_{digest:x}_{timestamp}"
        if profile == "md5":
            return hashlib.md5(raw.encode("utf-8")).hexdigest()  # noqa: S324 - deterministic fixture compatibility
        if profile == "sha1":
            return hashlib.sha1(raw.encode("utf-8")).hexdigest()  # noqa: S324 - deterministic fixture compatibility
        if profile in {"sha256", "webpack-minified"}:
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if profile == "base64":
            return base64.b64encode(raw.encode("utf-8")).decode("ascii")
        if profile == "context-localstorage":
            return base64.b64encode(f"{raw}:fixture-device".encode("utf-8")).decode("ascii")
        if profile == "context-cookie":
            return base64.b64encode(f"{raw}:fixture-cookie-device".encode("utf-8")).decode("ascii")
        if profile == "context-navigator":
            return hashlib.sha256(f"{raw}:ReverseDeepAgentMock/1.0".encode("utf-8")).hexdigest()
        if profile == "token-chain":
            return hashlib.sha256(f"{raw}:fixture-token".encode("utf-8")).hexdigest()
        if profile == "hybrid-context":
            return base64.b64encode(f"{raw}:fixture-nonce:fixture-csrf".encode("utf-8")).decode("ascii")
        return f"sig_{keyword}_{timestamp}"

    def _storage_payload(self) -> dict[str, Any]:
        profile = self._profile()
        local_storage: dict[str, str] = {}
        session_storage: dict[str, str] = {}
        cookies: dict[str, str] = {}
        if profile == "context-localstorage":
            local_storage["device_id"] = "fixture-device"
        elif profile == "hybrid-context":
            local_storage["fixture_nonce"] = "fixture-nonce"
            cookies["csrf_token"] = "fixture-csrf"
        if profile == "token-chain":
            session_storage["fixture_token"] = "fixture-token"
        if profile == "context-cookie":
            cookies["device_id"] = "fixture-cookie-device"
        return {
            "localStorage": local_storage,
            "sessionStorage": session_storage,
            "cookies": cookies,
        }

    def _runtime_environment(self) -> dict[str, Any]:
        profile = self._profile()
        cookie = ""
        local_storage: dict[str, str] = {}
        session_storage: dict[str, str] = {}
        if profile == "context-cookie":
            cookie = "device_id=fixture-cookie-device"
        elif profile == "context-localstorage":
            local_storage["device_id"] = "fixture-device"
        elif profile == "token-chain":
            session_storage["fixture_token"] = "fixture-token"
        elif profile == "hybrid-context":
            cookie = "csrf_token=fixture-csrf"
            local_storage["fixture_nonce"] = "fixture-nonce"
        return {
            "cookie": cookie,
            "localStorage": local_storage,
            "sessionStorage": session_storage,
            "navigator": {
                "userAgent": "ReverseDeepAgentMock/1.0",
                "platform": "MacIntel",
                "language": "zh-CN",
            },
            "timezoneOffset": -480,
        }

    def _is_fixture_url(self) -> bool:
        parsed = urlparse(self.active_url)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}

    @staticmethod
    def _fetch_text(url: str) -> str:
        with urlopen(url, timeout=5) as response:  # nosec B310 - local fixture smoke only
            return response.read().decode("utf-8")

    @staticmethod
    def _build_sign_line_number(source: str) -> int:
        for index, line in enumerate(source.splitlines(), start=1):
            if "function buildSign" in line:
                return index
        return 1

    @staticmethod
    def _line_at(source: str, line_number: int) -> str:
        lines = source.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""


def build_markdown_report(final_result: FinalResult) -> str:
    """Build a human-readable Markdown report from a final result."""

    findings = final_result.key_findings
    lines = [
        "# Reverse DeepAgent Demo Report",
        "",
        "## Task Card",
        f"- target_url_or_file: {final_result.task_card.target_url_or_file}",
        f"- target_param_or_api: {final_result.task_card.target_param_or_api}",
        f"- goal: {final_result.task_card.goal}",
        f"- boundaries: {final_result.task_card.boundaries}",
        f"- sample_request: {final_result.task_card.sample_request or ''}",
        f"- protection_hints: {', '.join(final_result.task_card.protection_hints)}",
        "",
        "## Result",
        f"- mode: {final_result.mode.value}",
        f"- stage: {final_result.stage.value}",
        f"- status: {final_result.status.value}",
        f"- confidence: {final_result.confidence.value}",
        f"- next_action: {final_result.next_action}",
        "",
        "## Facts",
    ]
    lines.extend([f"- {item}" for item in findings.facts] or ["- (none)"])
    lines.extend(["", "## Inferences"])
    lines.extend([f"- {item}" for item in findings.inferences] or ["- (none)"])
    lines.extend(["", "## Unknowns"])
    lines.extend([f"- {item}" for item in findings.unknowns] or ["- (none)"])
    return "\n".join(lines) + "\n"


def _mock_runtime_factory(**_: Any) -> JSReverserRuntime:
    return JSReverserRuntime(
        bridge=MockJSReverserBridge(),
        backend_id="mock",
        display_name="Mock JSReverser Runtime",
        transport="in-process",
    )


def _android_adb_runtime_factory(
    *,
    android_adb_command: str | None = None,
    android_device_serial: str | None = None,
    android_package_name: str | None = None,
    **_: Any,
) -> AndroidAdbRuntime:
    return AndroidAdbRuntime(
        adb_command=android_adb_command or "adb",
        device_serial=android_device_serial,
        package_name=android_package_name,
    )


def _ios_simulator_runtime_factory(
    *,
    ios_xcrun_command: str | None = None,
    ios_device_id: str | None = None,
    ios_bundle_id: str | None = None,
    **_: Any,
) -> IosSimulatorRuntime:
    return IosSimulatorRuntime(
        xcrun_command=ios_xcrun_command or "xcrun",
        device_id=ios_device_id,
        bundle_id=ios_bundle_id,
    )


def _mini_program_devtools_runtime_factory(
    *,
    mini_program_devtools_command: str | None = None,
    mini_program_vendor: str | None = None,
    mini_program_project_path: str | None = None,
    **_: Any,
) -> MiniProgramDevtoolsRuntime:
    return MiniProgramDevtoolsRuntime(
        devtools_command=mini_program_devtools_command,
        vendor=mini_program_vendor or "wechat",
        project_path=mini_program_project_path,
    )


def _playwright_cli_runtime_factory(
    *,
    playwright_command: str | None = None,
    request_timeout: float | None = None,
    **_: Any,
) -> JSReverserRuntime:
    config = LightweightWebRuntimeConfig(
        backend_id="playwright-cli",
        display_name="Playwright CLI Runtime",
        transport="playwright-cli",
        command=playwright_command or "playwright",
        command_args=["--version"],
        request_timeout=request_timeout or 10.0,
    )
    return create_lightweight_web_runtime(config=config)


def _chrome_cdp_runtime_factory(
    *,
    browser_url: str | None = None,
    cdp_browser_url: str | None = None,
    request_timeout: float | None = None,
    **_: Any,
) -> JSReverserRuntime:
    config = LightweightWebRuntimeConfig(
        backend_id="chrome-cdp",
        display_name="Chrome CDP Runtime",
        transport="chrome-cdp",
        browser_url=cdp_browser_url or browser_url or "http://127.0.0.1:9222",
        request_timeout=request_timeout or 10.0,
    )
    return create_lightweight_web_runtime(config=config)


def _browser_cli_runtime_factory(
    *,
    browser_cli_command: str | None = None,
    request_timeout: float | None = None,
    **_: Any,
) -> JSReverserRuntime:
    config = LightweightWebRuntimeConfig(
        backend_id="browser-cli",
        display_name="Generic Browser CLI Runtime",
        transport="browser-cli",
        command=browser_cli_command,
        command_args=["--version"] if browser_cli_command else [],
        request_timeout=request_timeout or 10.0,
    )
    return create_lightweight_web_runtime(config=config)


def _native_web_runtime_factory(
    *,
    browser: str | None = None,
    browser_provider: str | None = None,
    browser_headless: bool | None = None,
    browser_profile_dir: str | None = None,
    browser_executable_path: str | None = None,
    browser_args: list[str] | None = None,
    browser_url: str | None = None,
    cdp_browser_url: str | None = None,
    browser_humanize: bool | None = None,
    browser_proxy: str | None = None,
    browser_geoip: bool | None = None,
    browser_locale: str | None = None,
    browser_timezone: str | None = None,
    request_timeout: float | None = None,
    **_: Any,
):
    return create_native_web_runtime(
        browser=browser or browser_provider,
        browser_headless=True if browser_headless is None else browser_headless,
        browser_profile_dir=browser_profile_dir,
        browser_executable_path=browser_executable_path,
        browser_args=browser_args or [],
        browser_url=browser_url,
        cdp_browser_url=cdp_browser_url,
        browser_humanize=browser_humanize,
        browser_proxy=browser_proxy,
        browser_geoip=browser_geoip,
        browser_locale=browser_locale,
        browser_timezone=browser_timezone,
        request_timeout=request_timeout,
    )


def _remote_cdp_provider_runtime_factory(**kwargs: Any):
    kwargs.setdefault("browser", "remote-cdp")
    return _native_web_runtime_factory(**kwargs)


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


def legacy_mcp_alias_warning(runtime_kind: str) -> str | None:
    """Return the deprecation warning for legacy MCP aliases, if applicable."""

    return _legacy_mcp_alias_warning(runtime_kind)


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


def write_outputs(
    base_dir: Path,
    task_card: TaskCard,
    route_result: RouterResult,
    recon_result: ReconResult,
    final_result: FinalResult,
    export_bundle: dict[str, Any],
    runtime_capabilities: RuntimeBackendCapabilities | None = None,
    enable_workspace_dual_write: bool = False,
    workspace_dual_write_artifact_keys: Iterable[str] | None = None,
    browser_provider_smoke: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Persist the standard workspace/report/export artifact set."""

    workspace_dir = base_dir / "workspace"
    reports_dir = base_dir / "reports"
    exports_dir = base_dir / "exports"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    workspace_resolver = WorkspacePathResolver(
        enable_dual_write=enable_workspace_dual_write,
        dual_write_artifact_keys=workspace_dual_write_artifact_keys,
    )
    workspace_write_records: list[dict[str, Any]] = []
    report_json_path = reports_dir / "demo-final-result.json"
    report_md_path = reports_dir / "demo-final-report.md"
    index_path = exports_dir / "artifact-index.json"
    workspace_artifact_paths = _write_workspace_artifacts(base_dir, workspace_dir, final_result, workspace_resolver, workspace_write_records)
    rebuild_result = write_rebuild_bundle(base_dir, task_card, final_result)
    rebuild_artifact_paths = _rebuild_paths_from_result(rebuild_result)

    task_card_path = _write_workspace_json(base_dir, "workspace_task_card", task_card.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    route_path = _write_workspace_json(base_dir, "workspace_route", route_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    recon_path = _write_workspace_json(base_dir, "workspace_recon", recon_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    final_workspace_path = _write_workspace_json(base_dir, "workspace_final", final_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    workspace_contract_path = _write_workspace_json(base_dir, "workspace_workspace_contract", workspace_contract_payload(), workspace_resolver, workspace_write_records)
    evidence_promotion = promote_evidence(final_result.evidence, final_result.artifacts)
    evidence_artifact_paths = _write_evidence_promotion_artifacts(base_dir, workspace_dir, evidence_promotion, workspace_resolver, workspace_write_records)
    review_gate = evaluate_review_gate(rebuild_result, evidence_promotion)
    review_gate_path = _write_review_gate_artifact(base_dir, workspace_dir, review_gate, workspace_resolver, workspace_write_records)
    _write_json(report_json_path, final_result.model_dump(mode="json"))
    report_md_path.write_text(build_markdown_report(final_result), encoding="utf-8")

    output_paths = {
        "workspace_task_card": str(task_card_path),
        "workspace_route": str(route_path),
        "workspace_recon": str(recon_path),
        "workspace_final": str(final_workspace_path),
        "workspace_workspace_contract": str(workspace_contract_path),
        "json": str(report_json_path),
        "markdown": str(report_md_path),
        "index": str(index_path),
    }
    output_paths.update({f"workspace_{key}": value for key, value in workspace_artifact_paths.items()})
    output_paths.update({f"workspace_{key}": value for key, value in evidence_artifact_paths.items()})
    output_paths["workspace_review_gate"] = str(review_gate_path)
    output_paths.update({f"rebuild_{key}": value for key, value in rebuild_artifact_paths.items() if key != "rebuild_plan"})
    if "rebuild_plan" in rebuild_artifact_paths:
        output_paths["workspace_rebuild_plan"] = rebuild_artifact_paths["rebuild_plan"]
    capabilities = runtime_capabilities or RuntimeBackendCapabilities(backend_id="unknown", display_name="Unknown Runtime")
    browser_provider_smoke_path: Path | None = None
    browser_provider_smoke_attachment: dict[str, Any] | None = None
    browser_provider_smoke_acceptance: dict[str, Any] | None = None
    if browser_provider_smoke is not None:
        browser_provider_smoke_attachment = dict(browser_provider_smoke)
        browser_provider_smoke_acceptance = _browser_provider_smoke_acceptance(browser_provider_smoke_attachment, capabilities)
        browser_provider_smoke_attachment["attachment_acceptance"] = browser_provider_smoke_acceptance
        browser_provider_smoke_path = _write_workspace_json(
            base_dir,
            "workspace_browser_provider_smoke",
            browser_provider_smoke_attachment,
            workspace_resolver,
            workspace_write_records,
        )
        output_paths["workspace_browser_provider_smoke"] = str(browser_provider_smoke_path)
    if enable_workspace_dual_write:
        dual_write_plan_path = base_dir / "workspace" / "workspace-dual-write-plan.json"
        output_paths["workspace_dual_write_plan"] = str(dual_write_plan_path)
    manifest_path = base_dir / "workspace" / "backend-artifact-manifest.json"
    output_paths["workspace_backend_artifact_manifest"] = str(manifest_path)

    runtime_artifacts = export_bundle.get("artifacts", []) if isinstance(export_bundle, dict) else []
    backend_artifact_manifest = _build_backend_artifact_manifest(capabilities, output_paths, extra_artifacts=runtime_artifacts)
    manifest_path = _write_workspace_json(base_dir, "workspace_backend_artifact_manifest", backend_artifact_manifest.model_dump(mode="json"), workspace_resolver, workspace_write_records)

    artifact_index = {
        "workspace": {
            "task_card": str(task_card_path),
            "route_decision": str(route_path),
            "recon_result": str(recon_path),
            "final_result": str(final_workspace_path),
            "workspace_contract": str(workspace_contract_path),
        },
        "reports": {
            "json": str(report_json_path),
            "markdown": str(report_md_path),
        },
        "runtime_exports": export_bundle,
        "workspace_artifacts": workspace_artifact_paths,
        "evidence_promotion": evidence_promotion.model_dump(mode="json"),
        "evidence_artifacts": evidence_artifact_paths,
        "review_gate": review_gate.model_dump(mode="json"),
        "review_gate_artifact": str(review_gate_path),
        "rebuild_artifacts": rebuild_artifact_paths,
        "backend_artifact_manifest": str(manifest_path),
        "rebuild_result": rebuild_result.model_dump(mode="json"),
    }
    if browser_provider_smoke_path is not None:
        artifact_index["workspace"]["browser_provider_smoke"] = str(browser_provider_smoke_path)
        artifact_index["browser_provider_smoke"] = browser_provider_smoke_attachment
        artifact_index["browser_provider_smoke_acceptance"] = browser_provider_smoke_acceptance
    if enable_workspace_dual_write:
        dual_write_plan = _workspace_dual_write_plan_payload(
            workspace_write_records,
            dual_write_artifact_keys=workspace_dual_write_artifact_keys,
        )
        dual_write_plan_path = _write_workspace_json(base_dir, "workspace_dual_write_plan", dual_write_plan, workspace_resolver, workspace_write_records)
        artifact_index["workspace"]["dual_write_plan"] = str(dual_write_plan_path)
        artifact_index["workspace_dual_write"] = dual_write_plan
    _write_json(index_path, artifact_index)
    return output_paths


def _build_backend_artifact_manifest(
    capabilities: RuntimeBackendCapabilities,
    output_paths: dict[str, str],
    extra_artifacts: list[dict[str, Any]] | None = None,
) -> RuntimeArtifactManifest:
    entries = [
        RuntimeArtifactManifestEntry(
            artifact_key=key,
            path=path,
            category=_artifact_category_from_key(key),
            kind=_artifact_kind_from_path(path),
            producer_backend_id=capabilities.backend_id,
            producer_transport=capabilities.transport,
            target_platforms=capabilities.target_platforms,
            description=_artifact_description_from_key(key),
            metadata=_artifact_manifest_entry_metadata(capabilities, key, path),
        )
        for key, path in sorted(output_paths.items())
    ]
    entries.extend(_runtime_artifact_manifest_entries(capabilities, extra_artifacts or []))
    return RuntimeArtifactManifest(
        producer_backend_id=capabilities.backend_id,
        producer_transport=capabilities.transport,
        target_platforms=capabilities.target_platforms,
        entries=entries,
    )


ARTIFACT_CATEGORY_BY_KEY = {
    "workspace_network_requests": "network",
    "workspace_source_hits": "source",
    "workspace_source_contexts": "source",
    "workspace_script_inventory": "source",
    "workspace_response_bodies": "network",
    "workspace_websocket_frames": "network",
    "workspace_hook_timeline": "hook-timeline",
    "workspace_flow_timeline": "trace",
    "workspace_stitched_flow": "trace",
    "workspace_function_hooks": "hook-timeline",
    "workspace_function_hook_timeline": "hook-timeline",
    "workspace_module_hooks": "hook-timeline",
    "workspace_module_hook_timeline": "hook-timeline",
    "workspace_async_chunk_load_plan": "triage",
    "workspace_async_chunk_traversal_graph": "triage",
    "workspace_async_chunk_traversal_workflow_plan": "triage",
    "workspace_async_chunk_traversal_workflow_execution": "audit",
    "workspace_async_chunk_traversal_loop_plan": "triage",
    "workspace_async_chunk_traversal_loop_execution": "audit",
    "workspace_async_chunk_recursive_traversal_plan": "triage",
    "workspace_async_chunk_recursive_traversal_followup": "audit",
    "workspace_async_chunk_recursive_traversal_execution": "audit",
    "workspace_async_chunk_module_diff": "triage",
    "workspace_custom_loader_traversal_plan": "triage",
    "workspace_custom_loader_traversal_graph": "triage",
    "workspace_custom_loader_traversal_workflow_plan": "triage",
    "workspace_custom_loader_traversal_workflow_execution": "audit",
    "workspace_custom_loader_traversal_loop_plan": "triage",
    "workspace_custom_loader_traversal_loop_execution": "audit",
    "workspace_custom_loader_recursive_traversal_plan": "triage",
    "workspace_custom_loader_recursive_traversal_followup": "audit",
    "workspace_custom_loader_recursive_traversal_execution": "audit",
    "workspace_custom_loader_continuation_workflow": "triage",
    "workspace_custom_loader_continuation_journal": "audit",
    "workspace_custom_loader_continuation_execution": "audit",
    "workspace_custom_loader_execution_preflight": "triage",
    "workspace_custom_loader_execution_result": "trace",
    "workspace_custom_loader_module_diff": "triage",
    "workspace_module_federation_get_init_plan": "triage",
    "workspace_module_federation_get_init_result": "trace",
    "workspace_module_federation_factory_invoke_result": "trace",
    "workspace_module_federation_export_hook_plan": "triage",
    "workspace_module_federation_traversal_graph": "triage",
    "workspace_module_federation_traversal_workflow_plan": "triage",
    "workspace_module_federation_traversal_workflow_execution": "audit",
    "workspace_module_federation_recursive_traversal_plan": "triage",
    "workspace_module_federation_recursive_traversal_followup": "audit",
    "workspace_module_federation_recursive_traversal_execution": "audit",
    "workspace_module_federation_recursive_continuation_journal": "audit",
    "workspace_module_federation_recursive_continuation_checkpoint": "audit",
    "workspace_recursive_continuation_readiness": "audit",
    "workspace_async_chunk_load_result": "trace",
    "workspace_source_map_fetch_plan": "triage",
    "workspace_source_map_fetch_result": "trace",
    "workspace_source_map_lookup": "triage",
    "workspace_source_map_source_content": "triage",
    "workspace_source_map_readiness": "triage",
    "workspace_source_map_consumer_action_plan": "triage",
    "workspace_source_map_consumer_materialization": "triage",
    "workspace_source_map_typed_payload_preflight": "triage",
    "workspace_source_map_followthrough_review": "triage",
    "workspace_bundler_symbol_scope": "triage",
    "workspace_source_logpoints": "trace",
    "workspace_source_logpoint_timeline": "trace",
    "workspace_mutation_audit": "trace",
    "workspace_page_mutation_audit": "trace",
    "workspace_object_root_mutation_audit": "trace",
    "workspace_object_graph_diff": "triage",
    "workspace_mutation_observer_timeline": "trace",
    "workspace_breakpoints": "trace",
    "workspace_debugger_paused": "trace",
    "workspace_callframes": "trace",
    "workspace_callframe_evaluations": "trace",
    "workspace_debugger_actions": "trace",
    "workspace_debugger_session": "trace",
    "workspace_debugger_timeline": "trace",
    "workspace_paused_session_live_continuation_preflight": "audit",
    "workspace_paused_session_target_attach_readiness": "audit",
    "workspace_paused_session_cross_process_execution_plan": "triage",
    "workspace_paused_session_cross_process_session_lifecycle": "triage",
    "workspace_paused_session_cross_process_attach_probe": "audit",
    "workspace_paused_session_live_callframe_recovery": "audit",
    "workspace_paused_session_cross_process_one_action_execution": "audit",
    "workspace_paused_session_next_paused_event_capture_plan": "triage",
    "workspace_paused_session_next_paused_event_capture_execution": "audit",
    "workspace_paused_session_pre_action_subscribe_and_action": "audit",
    "workspace_paused_session_cross_process_continuation_checkpoint": "audit",
    "workspace_paused_session_multi_step_continuation_workflow": "triage",
    "workspace_paused_session_multi_step_continuation_execution": "audit",
    "workspace_paused_session_multi_step_loop_plan": "triage",
    "workspace_paused_session_multi_step_loop_execution": "audit",
    "workspace_paused_session_automatic_loop_readiness": "triage",
    "workspace_paused_session_automatic_loop_execution_plan": "triage",
    "workspace_paused_session_automatic_loop_executor_preflight": "triage",
    "workspace_paused_session_automatic_loop_executor_approval_plan": "triage",
    "workspace_paused_session_automatic_loop_executor_approval_record": "audit",
    "workspace_paused_session_automatic_loop_transaction_preflight": "audit",
    "workspace_paused_session_automatic_loop_executor_journal": "audit",
    "workspace_paused_session_automatic_loop_bounded_executor_gate": "audit",
    "workspace_paused_session_automatic_loop_execution_result": "audit",
    "workspace_paused_session_automatic_loop_followup_checkpoint": "audit",
    "workspace_paused_session_automatic_loop_next_iteration_plan": "triage",
    "workspace_paused_session_automatic_loop_next_iteration_execution": "audit",
    "workspace_paused_session_automatic_loop_next_iteration_followup_checkpoint": "audit",
    "workspace_paused_session_automatic_loop_following_iteration_plan": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_policy": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_preflight": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_execution_plan": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_approval_plan": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_approval_record": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_transaction_preflight": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_journal": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_bounded_executor_gate": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_execution_result": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_followup_checkpoint": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_next_step_plan": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_input_preflight": "triage",
    "workspace_closure_functions": "trace",
    "workspace_closure_function_candidates": "triage",
    "workspace_closure_wrapper_replacement_plan": "triage",
    "workspace_closure_wrapper_assignment_safety": "triage",
    "workspace_closure_wrapper_runtime_mutability_preflight": "triage",
    "workspace_closure_wrapper_runtime_mutability_result": "audit",
    "workspace_closure_wrapper_replacement_execution": "audit",
    "workspace_closure_wrapper_restore_plan": "audit",
    "workspace_closure_wrapper_restore_execution": "audit",
    "workspace_closure_wrapper_events": "hook-timeline",
    "workspace_closure_wrapper_continuation_readiness": "triage",
    "workspace_closure_wrapper_continuation_execution_plan": "triage",
    "workspace_closure_wrapper_continuation_execution": "audit",
    "workspace_closure_wrapper_continuation_checkpoint": "triage",
    "workspace_closure_wrapper_continuation_next_iteration_plan": "triage",
    "workspace_closure_wrapper_continuation_next_iteration_execution": "audit",
    "workspace_request_initiators": "trace",
    "workspace_navigation_events": "trace",
    "workspace_browser_provider_smoke": "runtime-context",
    "workspace_runtime_context": "runtime-context",
    "workspace_dom_snapshot": "runtime-context",
    "workspace_console_messages": "runtime-context",
    "workspace_runtime_context_diff": "runtime-context",
    "workspace_runtime_capabilities": "runtime-context",
    "workspace_runtime_export_bundle": "export",
    "workspace_workspace_contract": "workspace",
    "workspace_platform_tool_probe": "runtime-context",
    "workspace_function_candidates": "source",
    "workspace_function_validations": "trace",
    "workspace_function_validation_summary": "trace",
    "workspace_evidence_candidates": "evidence",
    "workspace_evidence_validated": "evidence",
    "workspace_evidence_promotion": "evidence",
    "workspace_stitched_flow_physical_rollback_diff": "trace",
    "workspace_stitched_flow_physical_rollback_results": "trace",
    "workspace_review_gate_after_rollback": "triage",
    "workspace_review_gate_after_physical_rollback": "triage",
    "workspace_review_gate_replacement_results": "triage",
    "workspace_delivery_guard_after_review_gate_replacement": "triage",
    "workspace_final_delivery_package_after_review_gate_replacement": "export",
    "workspace_final_delivery_transaction_commit": "export",
    "workspace_delivery_receipt": "export",
    "workspace_delivery_transaction_journal": "export",
    "workspace_external_delivery_result": "export",
    "workspace_external_delivery_duplicate_guard": "export",
    "workspace_delivery_manifest_revision": "export",
    "workspace_backend_artifact_manifest_mutation": "export",
    "workspace_backend_artifact_manifest_patched": "export",
    "workspace_backend_artifact_manifest_preflight": "triage",
    "workspace_backend_artifact_manifest_in_place_mutation": "export",
    "workspace_backend_artifact_manifest_rollback": "export",
    "workspace_backend_artifact_manifest_recovery_preflight": "triage",
    "workspace_backend_artifact_manifest_recovery": "export",
    "workspace_backend_artifact_manifest_transaction_commit": "export",
    "workspace_review_gate": "triage",
}


def _artifact_manifest_entry_metadata(capabilities: RuntimeBackendCapabilities, artifact_key: str, path: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"path_style": "virtual" if path.startswith("virtual://") else "filesystem"}
    metadata.update(workspace_manifest_alias_metadata(artifact_key))
    provider = capabilities.config.get("provider") if isinstance(capabilities.config, dict) else None
    if isinstance(provider, dict):
        provider_id = provider.get("provider_id")
        if provider_id:
            metadata["browser_provider"] = provider_id
        provider_transport = provider.get("transport")
        if provider_transport:
            metadata["browser_provider_transport"] = provider_transport
    return metadata


def _browser_provider_smoke_acceptance(smoke_payload: dict[str, Any], capabilities: RuntimeBackendCapabilities) -> dict[str, Any]:
    """Review existing BrowserProvider smoke JSON before attaching it to Web artifacts.

    This is deliberately a metadata-only acceptance gate. It does not generate
    smoke evidence, call provider factories, check availability, probe CDP,
    launch browsers, call MCP, or inspect mobile runtimes.
    """

    provider = capabilities.config.get("provider") if isinstance(capabilities.config, dict) else None
    expected_provider_id = str(provider.get("provider_id") or "") if isinstance(provider, dict) else ""
    resolved_provider_id = str(smoke_payload.get("resolved_provider_id") or "")
    requested_provider_id = str(smoke_payload.get("requested_provider_id") or "")
    mode = str(smoke_payload.get("mode") or "unknown")
    schema_version = str(smoke_payload.get("schema_version") or "")
    side_effect_policy = smoke_payload.get("side_effect_policy") if isinstance(smoke_payload.get("side_effect_policy"), dict) else {}
    provider_row = smoke_payload.get("provider") if isinstance(smoke_payload.get("provider"), dict) else {}
    provider_smoke = provider_row.get("smoke") if isinstance(provider_row.get("smoke"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []
    if schema_version != "reverse-deepagent.browser-provider-smoke.v1":
        blockers.append("browser_provider_smoke_schema_mismatch")
    if not bool(smoke_payload.get("ok")):
        blockers.append("browser_provider_smoke_not_ok")
    if not resolved_provider_id:
        blockers.append("resolved_provider_id_missing")
    if expected_provider_id and resolved_provider_id and expected_provider_id != resolved_provider_id:
        blockers.append("browser_provider_smoke_provider_mismatch")
    if bool(side_effect_policy.get("calls_mcp")):
        blockers.append("browser_provider_smoke_calls_mcp")
    if bool(side_effect_policy.get("touches_mobile_full_runtime_chains")):
        blockers.append("browser_provider_smoke_touches_mobile_full_runtime_chain")
    if mode == "launch-smoke":
        if not bool(side_effect_policy.get("launch_smoke_requested")):
            blockers.append("launch_smoke_mode_without_launch_request")
        if provider_smoke and provider_smoke.get("status") != "passed":
            blockers.append("launch_smoke_not_passed")
        if not provider_smoke:
            warnings.append("launch_smoke_result_not_embedded")
    elif bool(side_effect_policy.get("starts_browser")):
        blockers.append("browser_started_outside_launch_smoke_mode")
    if mode == "metadata-only":
        warnings.append("metadata_only_evidence_not_launch_smoke")
    if mode == "availability-check":
        warnings.append("availability_check_evidence_not_launch_smoke")
    if not expected_provider_id:
        warnings.append("runtime_provider_not_comparable")

    evidence_level = mode if mode in {"metadata-only", "availability-check", "launch-smoke"} else "unknown"
    accepted = not blockers
    launch_smoke_accepted = accepted and evidence_level == "launch-smoke"
    status = "accepted" if accepted else "blocked"
    next_action = (
        "review_browser_provider_launch_smoke_result"
        if launch_smoke_accepted
        else "optionally_run_explicit_launch_browser_smoke"
        if accepted
        else "regenerate_browser_provider_smoke_evidence"
    )
    return {
        "schema_version": "reverse-deepagent.browser-provider-smoke-acceptance.v1",
        "status": status,
        "accepted": accepted,
        "runtime_launch_smoke_accepted": launch_smoke_accepted,
        "evidence_level": evidence_level,
        "expected_provider_id": expected_provider_id or None,
        "requested_provider_id": requested_provider_id or None,
        "resolved_provider_id": resolved_provider_id or None,
        "provider_match": bool(not expected_provider_id or expected_provider_id == resolved_provider_id),
        "blockers": blockers,
        "warnings": sorted(set(warnings)),
        "side_effect_policy": {
            "metadata_only": True,
            "generates_smoke": False,
            "provider_factory_invoked": False,
            "availability_checked": False,
            "cdp_endpoint_probed": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
        "next_action": next_action,
    }


def _artifact_category_from_key(key: str) -> str:
    if key in ARTIFACT_CATEGORY_BY_KEY:
        return ARTIFACT_CATEGORY_BY_KEY[key]
    if key.startswith("workspace_"):
        return "workspace"
    if key.startswith("rebuild_"):
        return "rebuild"
    if key in {"json", "markdown"}:
        return "report"
    if key == "index":
        return "export"
    return "other"


def _artifact_kind_from_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".py":
        return "rebuild"
    return "other"


def _runtime_artifact_manifest_entries(
    capabilities: RuntimeBackendCapabilities,
    artifacts: list[dict[str, Any]],
) -> list[RuntimeArtifactManifestEntry]:
    entries: list[RuntimeArtifactManifestEntry] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            continue
        path = str(artifact.get("path") or "")
        if not path:
            continue
        metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
        artifact_key = str(
            artifact.get("artifact_key")
            or metadata.get("artifact_key")
            or _artifact_key_from_runtime_path(path, index)
        )
        entry_metadata = dict(metadata)
        entry_metadata.setdefault("path_style", "virtual" if path.startswith("virtual://") else "filesystem")
        entry_metadata.setdefault("source", "runtime_export_bundle")
        entries.append(
            RuntimeArtifactManifestEntry(
                artifact_key=artifact_key,
                path=path,
                category=_artifact_category_from_runtime_artifact(path, artifact, metadata),
                kind=str(artifact.get("kind") or _artifact_kind_from_path(path)),
                producer_backend_id=capabilities.backend_id,
                producer_transport=capabilities.transport,
                target_platforms=capabilities.target_platforms,
                description=artifact.get("description"),
                metadata=entry_metadata,
            )
        )
    return entries


def _artifact_key_from_runtime_path(path: str, index: int) -> str:
    normalized = path
    for prefix in ("virtual://", "file://"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    normalized = normalized.strip("/") or f"artifact_{index}"
    stem = Path(normalized).with_suffix("").as_posix()
    safe = "".join(ch if ch.isalnum() else "_" for ch in stem).strip("_")
    return f"runtime_{safe or f'artifact_{index}'}"


def _artifact_category_from_runtime_artifact(path: str, artifact: dict[str, Any], metadata: dict[str, Any]) -> str:
    explicit_category = artifact.get("category") or metadata.get("category")
    if explicit_category:
        return str(explicit_category)
    if path.startswith("virtual://exports/session"):
        return "session"
    if path.startswith("virtual://exports/"):
        return "export"
    if path.startswith("virtual://workspace/"):
        return _artifact_category_from_key(_artifact_key_from_runtime_path(path, 0))
    if path.startswith("virtual://protection/"):
        return "triage"
    return "other"


def _artifact_description_from_key(key: str) -> str:
    return key.replace("_", " ")



def build_platform_markdown_report(final_result: FinalResult, capabilities: RuntimeBackendCapabilities) -> str:
    """Build a human-readable Markdown report for the platform-neutral pipeline."""

    findings = final_result.key_findings
    lines = [
        "# Reverse DeepAgent Platform Pipeline Report",
        "",
        "## Runtime",
        f"- backend_id: {capabilities.backend_id}",
        f"- display_name: {capabilities.display_name}",
        f"- transport: {capabilities.transport}",
        f"- target_platforms: {', '.join(capabilities.target_platforms) or '(unknown)'}",
        f"- supports_browser_session: {capabilities.supports_browser_session}",
        f"- supports_web_recon: {capabilities.supports_web_recon}",
        f"- supports_artifact_export: {capabilities.supports_artifact_export}",
        "",
        "## Task Card",
        f"- target_url_or_file: {final_result.task_card.target_url_or_file}",
        f"- target_param_or_api: {final_result.task_card.target_param_or_api}",
        f"- goal: {final_result.task_card.goal}",
        f"- boundaries: {final_result.task_card.boundaries}",
        f"- sample_request: {final_result.task_card.sample_request or ''}",
        f"- protection_hints: {', '.join(final_result.task_card.protection_hints)}",
        "",
        "## Result",
        f"- mode: {final_result.mode.value}",
        f"- stage: {final_result.stage.value}",
        f"- status: {final_result.status.value}",
        f"- confidence: {final_result.confidence.value}",
        f"- next_action: {final_result.next_action}",
        "",
        "## Facts",
    ]
    lines.extend([f"- {item}" for item in findings.facts] or ["- (none)"])
    lines.extend(["", "## Inferences"])
    lines.extend([f"- {item}" for item in findings.inferences] or ["- (none)"])
    lines.extend(["", "## Unknowns"])
    lines.extend([f"- {item}" for item in findings.unknowns] or ["- (none)"])
    return "\n".join(lines) + "\n"


def run_platform_pipeline(
    task_text: str,
    artifact_root: Path,
    runtime_kind: str = "android-adb",
    runtime: ReverseRuntime | None = None,
    enable_workspace_dual_write: bool = False,
    workspace_dual_write_artifact_keys: Iterable[str] | None = None,
    **runtime_kwargs: Any,
) -> PlatformPipelineOutput:
    """Run a platform-neutral runtime pipeline without assuming browser/Web recon semantics.

    The pipeline performs task normalization, route selection, capability capture,
    runtime artifact export, and standard artifact persistence for any
    :class:`ReverseRuntime`. It intentionally does not call Web-only methods such
    as ``ensure_browser_session`` or ``run_web_recon``.
    """

    task_card = normalize_task_card(task_text)
    route_result = route_from_task_card(task_card, task_text=task_text)
    active_runtime = runtime or build_runtime(runtime_kind, **runtime_kwargs)
    capabilities = active_runtime.describe_capabilities()
    export_bundle = active_runtime.export_reverse_artifacts(final_result=None)
    final_result = _final_from_runtime_export(task_card, route_result, capabilities, export_bundle)
    export_bundle = export_bundle.model_copy(update={"final_result": final_result})
    paths = write_platform_outputs(
        artifact_root,
        task_card,
        route_result,
        final_result,
        capabilities,
        export_bundle,
        enable_workspace_dual_write=enable_workspace_dual_write,
        workspace_dual_write_artifact_keys=workspace_dual_write_artifact_keys,
    )
    return PlatformPipelineOutput(
        final_result=final_result,
        artifacts=paths,
        runtime_capabilities=capabilities,
        runtime_export_bundle=export_bundle,
    )


def write_platform_outputs(
    base_dir: Path,
    task_card: TaskCard,
    route_result: RouterResult,
    final_result: FinalResult,
    runtime_capabilities: RuntimeBackendCapabilities,
    export_bundle: RuntimeExportBundle,
    enable_workspace_dual_write: bool = False,
    workspace_dual_write_artifact_keys: Iterable[str] | None = None,
) -> dict[str, str]:
    """Persist the platform-neutral workspace/report/export artifact set."""

    workspace_dir = base_dir / "workspace"
    reports_dir = base_dir / "reports"
    exports_dir = base_dir / "exports"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    workspace_resolver = WorkspacePathResolver(
        enable_dual_write=enable_workspace_dual_write,
        dual_write_artifact_keys=workspace_dual_write_artifact_keys,
    )
    workspace_write_records: list[dict[str, Any]] = []
    report_json_path = reports_dir / "platform-pipeline-result.json"
    report_md_path = reports_dir / "platform-pipeline-report.md"
    index_path = exports_dir / "artifact-index.json"

    export_payload = export_bundle.model_dump(mode="json")
    task_card_path = _write_workspace_json(base_dir, "workspace_task_card", task_card.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    route_path = _write_workspace_json(base_dir, "workspace_route", route_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    capabilities_path = _write_workspace_json(base_dir, "workspace_runtime_capabilities", runtime_capabilities.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    export_bundle_path = _write_workspace_json(base_dir, "workspace_runtime_export_bundle", export_payload, workspace_resolver, workspace_write_records)
    final_workspace_path = _write_workspace_json(base_dir, "workspace_final", final_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    workspace_contract_path = _write_workspace_json(base_dir, "workspace_workspace_contract", workspace_contract_payload(), workspace_resolver, workspace_write_records)
    evidence_promotion = promote_evidence(final_result.evidence, final_result.artifacts)
    evidence_artifact_paths = _write_evidence_promotion_artifacts(base_dir, workspace_dir, evidence_promotion, workspace_resolver, workspace_write_records)
    _write_json(report_json_path, final_result.model_dump(mode="json"))
    report_md_path.write_text(build_platform_markdown_report(final_result, runtime_capabilities), encoding="utf-8")

    output_paths = {
        "workspace_task_card": str(task_card_path),
        "workspace_route": str(route_path),
        "workspace_runtime_capabilities": str(capabilities_path),
        "workspace_runtime_export_bundle": str(export_bundle_path),
        "workspace_final": str(final_workspace_path),
        "workspace_workspace_contract": str(workspace_contract_path),
        "json": str(report_json_path),
        "markdown": str(report_md_path),
        "index": str(index_path),
    }
    output_paths.update({f"workspace_{key}": value for key, value in evidence_artifact_paths.items()})
    platform_probe_path = _write_platform_tool_probe_if_present(base_dir, workspace_dir, export_bundle, workspace_resolver, workspace_write_records)
    if platform_probe_path is not None:
        output_paths["workspace_platform_tool_probe"] = str(platform_probe_path)
    if enable_workspace_dual_write:
        output_paths["workspace_dual_write_plan"] = str(base_dir / "workspace" / "workspace-dual-write-plan.json")
    manifest_path = base_dir / "workspace" / "backend-artifact-manifest.json"
    output_paths["workspace_backend_artifact_manifest"] = str(manifest_path)

    manifest = _build_backend_artifact_manifest(
        runtime_capabilities,
        output_paths,
        extra_artifacts=export_payload.get("artifacts", []),
    )
    manifest_path = _write_workspace_json(base_dir, "workspace_backend_artifact_manifest", manifest.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    artifact_index = {
        "workspace": {
            "task_card": str(task_card_path),
            "route_decision": str(route_path),
            "runtime_capabilities": str(capabilities_path),
            "runtime_export_bundle": str(export_bundle_path),
            "final_result": str(final_workspace_path),
            "workspace_contract": str(workspace_contract_path),
            "platform_tool_probe": str(platform_probe_path) if platform_probe_path is not None else None,
        },
        "reports": {
            "json": str(report_json_path),
            "markdown": str(report_md_path),
        },
        "runtime_exports": export_payload,
        "evidence_promotion": evidence_promotion.model_dump(mode="json"),
        "evidence_artifacts": evidence_artifact_paths,
        "backend_artifact_manifest": str(manifest_path),
    }
    if enable_workspace_dual_write:
        dual_write_plan = _workspace_dual_write_plan_payload(
            workspace_write_records,
            dual_write_artifact_keys=workspace_dual_write_artifact_keys,
        )
        dual_write_plan_path = _write_workspace_json(base_dir, "workspace_dual_write_plan", dual_write_plan, workspace_resolver, workspace_write_records)
        artifact_index["workspace"]["dual_write_plan"] = str(dual_write_plan_path)
        artifact_index["workspace_dual_write"] = dual_write_plan
    _write_json(index_path, artifact_index)
    return output_paths


def _write_platform_tool_probe_if_present(
    base_dir: Path,
    workspace_dir: Path,
    export_bundle: RuntimeExportBundle,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> Path | None:
    for item in export_bundle.exports:
        if not isinstance(item, dict):
            continue
        if item.get("tool") != "platform_tool_probe":
            continue
        return _write_workspace_json(base_dir, "workspace_platform_tool_probe", item.get("payload", {}), resolver, write_records)
    return None



def _artifact_refs_from_runtime_export(export_bundle: RuntimeExportBundle) -> list[ArtifactRef]:
    artifact_refs: list[ArtifactRef] = []
    for artifact in export_bundle.artifacts:
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("path")
        if not path:
            continue
        artifact_refs.append(
            ArtifactRef(
                path=str(path),
                kind=artifact.get("kind") or ArtifactKind.OTHER,
                description=artifact.get("description"),
                metadata=artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {},
            )
        )
    return artifact_refs

def _final_from_runtime_export(
    task_card: TaskCard,
    route_result: RouterResult,
    capabilities: RuntimeBackendCapabilities,
    export_bundle: RuntimeExportBundle,
) -> FinalResult:
    probe = _platform_tool_probe_from_export(export_bundle)
    artifacts = _artifact_refs_from_runtime_export(export_bundle)
    export_count = len(export_bundle.exports)
    artifact_count = len(export_bundle.artifacts)
    facts = [
        f"Runtime backend '{capabilities.backend_id}' uses transport '{capabilities.transport}'.",
        f"Target platforms: {', '.join(capabilities.target_platforms) or 'unknown'}.",
        f"Runtime export emitted {export_count} export payload(s) and {artifact_count} artifact reference(s).",
    ]
    evidence_details: dict[str, Any] = {
        "capabilities": capabilities.model_dump(mode="json"),
        "export_count": export_count,
        "artifact_count": artifact_count,
    }
    status = ExecutionStatus.SUCCESS if artifact_count or export_count else ExecutionStatus.PARTIAL
    confidence = ConfidenceLevel.MEDIUM
    next_action = "inspect_runtime_export_bundle"
    unknowns: list[str] = []
    inferences = [
        "The platform-neutral pipeline completed without invoking Web-only browser recon methods.",
    ]
    if probe is not None:
        available = bool(probe.get("available"))
        facts.append(f"Platform toolchain available: {available}.")
        evidence_details["platform_tool_probe"] = probe
        if available:
            next_action = "continue_with_platform_specific_recon_or_hooking"
            confidence = ConfidenceLevel.MEDIUM
        else:
            status = ExecutionStatus.PARTIAL
            next_action = "install_or_configure_platform_tooling"
            confidence = ConfidenceLevel.LOW
            unknowns.append("Runtime-specific recon/hooking cannot proceed until the local platform toolchain is available.")
    elif not capabilities.supports_artifact_export and not (artifact_count or export_count):
        status = ExecutionStatus.PARTIAL
        confidence = ConfidenceLevel.LOW
        unknowns.append("Runtime does not advertise artifact export support; only capability metadata was captured.")

    evidence = [
        EvidenceItem(
            summary=f"Captured capability metadata for runtime backend {capabilities.backend_id}.",
            kind=EvidenceKind.NOTE,
            source="runtime_capabilities",
            anchor=capabilities.backend_id,
            details=capabilities.model_dump(mode="json"),
            confidence=ConfidenceLevel.HIGH,
        ),
        EvidenceItem(
            summary=f"Captured runtime export bundle with {export_count} export payload(s).",
            kind=EvidenceKind.OTHER,
            source="runtime_export_bundle",
            anchor=capabilities.backend_id,
            details=evidence_details,
            confidence=confidence,
        ),
    ]
    if probe is not None:
        evidence.append(
            EvidenceItem(
                summary="Captured side-effect-light platform toolchain probe.",
                kind=EvidenceKind.DYNAMIC,
                source="platform_tool_probe",
                anchor=capabilities.backend_id,
                details=probe,
                confidence=ConfidenceLevel.MEDIUM if probe.get("available") else ConfidenceLevel.LOW,
            )
        )
    return FinalResult(
        task_card=task_card,
        mode=route_result.selected_mode,
        stage=ReverseStage.CONTEXT,
        status=status,
        key_findings=KeyFindings(facts=facts, inferences=inferences, unknowns=unknowns),
        evidence=evidence,
        artifacts=artifacts,
        next_action=next_action,
        confidence=confidence,
    )


def _platform_tool_probe_from_export(export_bundle: RuntimeExportBundle) -> dict[str, Any] | None:
    for item in export_bundle.exports:
        if not isinstance(item, dict):
            continue
        if item.get("tool") == "platform_tool_probe" and isinstance(item.get("payload"), dict):
            return item["payload"]
    return None

def run_reverse_pipeline(
    task_text: str,
    artifact_root: Path,
    runtime_kind: str = "mock",
    chrome_config: ChromeDebugConfig | None = None,
    ensure_chrome: bool = False,
    keep_chrome: bool = False,
    mcp_command: str | None = None,
    runtime: WebReverseRuntime | None = None,
    enable_workspace_dual_write: bool = False,
    workspace_dual_write_artifact_keys: Iterable[str] | None = None,
    browser_provider_smoke: dict[str, Any] | None = None,
    **runtime_kwargs: Any,
) -> ReversePipelineOutput:
    """Run the deterministic reverse coordinator pipeline.

    This function is the stable package-level orchestration entry for scripts,
    tests, and future deepagents wrappers. It performs task normalization,
    routing, Web recon, final result assembly, runtime artifact export, and
    standard output persistence.
    """

    task_card = normalize_task_card(task_text)
    route_result = route_from_task_card(task_card, task_text=task_text)
    chrome_launch = None
    chrome_stop = None
    should_stop_chrome = False
    owns_runtime = runtime is None
    active_runtime = runtime or build_runtime(
        runtime_kind,
        browser_url=chrome_config.browser_url if chrome_config else None,
        mcp_command=mcp_command,
        **runtime_kwargs,
    )
    try:
        if not isinstance(active_runtime, WebReverseRuntime):
            capabilities = active_runtime.describe_capabilities()
            raise TypeError(
                f"Runtime backend {capabilities.backend_id!r} does not implement WebReverseRuntime; "
                "run_reverse_pipeline is the Web pipeline entrypoint."
            )
        runtime_capabilities = active_runtime.describe_capabilities()

        if _is_legacy_mcp_runtime_kind(runtime_kind) and ensure_chrome:
            chrome_launch = ensure_chrome_debug(chrome_config)
            if not chrome_launch.ok:
                raise RuntimeError(f"Failed to ensure Chrome debug session: {chrome_launch.stderr or chrome_launch.stdout}")
            should_stop_chrome = not keep_chrome

        recon_result = active_runtime.run_web_recon(task_card=task_card, route_result=route_result)
        final_result = _final_from_recon(task_card, route_result, recon_result)
        export_bundle = active_runtime.export_reverse_artifacts(final_result=final_result).model_dump(mode="json")
    finally:
        if owns_runtime:
            close = getattr(active_runtime, "close", None)
            if callable(close):
                close()
        if should_stop_chrome:
            chrome_stop = stop_chrome_debug(chrome_config)

    paths = write_outputs(
        artifact_root,
        task_card,
        route_result,
        recon_result,
        final_result,
        export_bundle,
        runtime_capabilities=runtime_capabilities,
        enable_workspace_dual_write=enable_workspace_dual_write,
        workspace_dual_write_artifact_keys=workspace_dual_write_artifact_keys,
        browser_provider_smoke=browser_provider_smoke,
    )
    return ReversePipelineOutput(
        final_result=final_result,
        artifacts=paths,
        chrome_launch=chrome_launch,
        chrome_stop=chrome_stop,
    )


def _is_legacy_mcp_runtime_kind(runtime_kind: str) -> bool:
    return is_legacy_mcp_runtime_kind(runtime_kind)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_workspace_json(
    base_dir: Path,
    artifact_key: str,
    payload: Any,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> Path:
    resolution = resolver.resolve_artifact_key(artifact_key)
    if resolution is None:
        fallback_path = base_dir / "workspace" / f"{artifact_key.removeprefix('workspace_').replace('_', '-')}.json"
        _write_json(fallback_path, payload)
        return fallback_path

    canonical_path = base_dir / resolution.legacy_path
    written_paths: list[str] = []
    for write_path in resolution.write_paths:
        target_path = _workspace_filesystem_path(base_dir, write_path)
        _write_json(target_path, payload)
        written_paths.append(str(target_path))
    write_records.append(
        {
            "artifact_key": artifact_key,
            "canonical_path": str(canonical_path),
            "future_path": str(_workspace_filesystem_path(base_dir, resolution.future_path)),
            "virtual_uri": resolution.virtual_uri,
            "write_paths": written_paths,
            "dual_write_enabled": resolution.dual_write_enabled,
            "dual_write_scope_enabled": resolution.dual_write_scope_enabled,
            "dual_write_in_scope": resolution.dual_write_in_scope,
            "physical_migration_enabled": resolution.physical_migration_enabled,
            "canonical_path_remains_authoritative": resolution.canonical_path_remains_authoritative,
            "migration_status": resolution.migration_status,
        }
    )
    return canonical_path


def _workspace_filesystem_path(base_dir: Path, workspace_path: str) -> Path:
    if workspace_path.startswith("virtual://workspace/"):
        return base_dir / workspace_path.removeprefix("virtual://")
    if workspace_path.startswith("/workspace/"):
        return base_dir / workspace_path.lstrip("/")
    if workspace_path.startswith("workspace/"):
        return base_dir / workspace_path
    return base_dir / "workspace" / workspace_path


def _workspace_dual_write_plan_payload(
    write_records: list[dict[str, Any]],
    *,
    dual_write_artifact_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    dual_written = [record for record in write_records if record.get("dual_write_enabled")]
    scoped = dual_write_artifact_keys is not None
    scope_keys = sorted(str(key) for key in dual_write_artifact_keys or [] if str(key))
    out_of_scope = [
        record
        for record in write_records
        if scoped and record.get("artifact_key") not in set(scope_keys)
    ]
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
        "status": "applied" if dual_written else "not-enabled",
        "mode": "scoped-opt-in-dual-write" if scoped else "opt-in-dual-write",
        "canonical_path_remains_authoritative": True,
        "physical_migration_enabled": False,
        "dual_write_scope_enabled": scoped,
        "dual_write_scope_artifact_keys": scope_keys,
        "record_count": len(write_records),
        "dual_written_count": len(dual_written),
        "out_of_scope_record_count": len(out_of_scope),
        "records": write_records,
    }


def _workspace_artifact_key_from_filename(filename: str) -> str:
    return f"workspace_{filename.removesuffix('.json').replace('-', '_').replace('.', '_')}"


def _write_evidence_promotion_artifacts(
    base_dir: Path,
    workspace_dir: Path,
    evidence_promotion: Any,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> dict[str, str]:
    paths: dict[str, str] = {}
    for filename, payload in promotion_workspace_payloads(evidence_promotion).items():
        artifact_key = _workspace_artifact_key_from_filename(filename)
        path = _write_workspace_json(base_dir, artifact_key, payload, resolver, write_records)
        paths[filename.removesuffix(".json").replace("-", "_")] = str(path)
    return paths


def _write_review_gate_artifact(
    base_dir: Path,
    workspace_dir: Path,
    review_gate: Any,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> Path:
    return _write_workspace_json(base_dir, "workspace_review_gate", review_gate_workspace_payload(review_gate), resolver, write_records)


def _write_workspace_artifacts(
    base_dir: Path,
    workspace_dir: Path,
    final_result: FinalResult,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> dict[str, str]:
    payloads = _extract_workspace_artifact_payloads(final_result)
    paths: dict[str, str] = {}
    for filename, payload in payloads.items():
        artifact_key = _workspace_artifact_key_from_filename(filename)
        path = _write_workspace_json(base_dir, artifact_key, payload, resolver, write_records)
        paths[filename.removesuffix(".json").replace("-", "_")] = str(path)
    return paths


def _rebuild_paths_from_result(rebuild_result: Any) -> dict[str, str]:
    paths: dict[str, str] = {}
    generated_files = getattr(rebuild_result, "generated_files", None) or {}
    for key, value in generated_files.items():
        paths[key] = value
    return paths


def _extract_workspace_artifact_payloads(final_result: FinalResult) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    for evidence in final_result.evidence:
        if evidence.source == "network_request":
            payloads["network-requests.json"] = evidence.details
        elif evidence.source == "search_in_sources":
            payloads["source-hits.json"] = evidence.details
        elif evidence.source == "get_request_initiator":
            payloads["request-initiators.json"] = evidence.details
        elif evidence.source == "get_script_source":
            payloads["source-contexts.json"] = evidence.details
        elif evidence.source == "response_body_metadata":
            payloads["response-bodies.json"] = evidence.details
        elif evidence.source == "websocket_frame_metadata":
            payloads["websocket-frames.json"] = evidence.details
        elif evidence.source == "runtime_hook_timeline":
            payloads["hook-timeline.json"] = evidence.details
        elif evidence.source == "flow_timeline":
            payloads["flow-timeline.json"] = evidence.details
        elif evidence.source == "stitched_flow":
            payloads["stitched-flow.json"] = evidence.details
        elif evidence.source == "function_hooks":
            payloads["function-hooks.json"] = evidence.details
        elif evidence.source == "function_hook_timeline":
            payloads["function-hook-timeline.json"] = evidence.details
        elif evidence.source == "async_chunk_load_plan":
            payloads["async-chunk-load-plan.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_graph":
            payloads["async-chunk-traversal-graph.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_workflow_plan":
            payloads["async-chunk-traversal-workflow-plan.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_workflow_execution":
            payloads["async-chunk-traversal-workflow-execution.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_loop_plan":
            payloads["async-chunk-traversal-loop-plan.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_loop_execution":
            payloads["async-chunk-traversal-loop-execution.json"] = evidence.details
        elif evidence.source == "async_chunk_recursive_traversal_plan":
            payloads["async-chunk-recursive-traversal-plan.json"] = evidence.details
        elif evidence.source == "async_chunk_recursive_traversal_followup":
            payloads["async-chunk-recursive-traversal-followup.json"] = evidence.details
        elif evidence.source == "async_chunk_recursive_traversal_execution":
            payloads["async-chunk-recursive-traversal-execution.json"] = evidence.details
        elif evidence.source == "async_chunk_module_diff":
            payloads["async-chunk-module-diff.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_plan":
            payloads["custom-loader-traversal-plan.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_graph":
            payloads["custom-loader-traversal-graph.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_workflow_plan":
            payloads["custom-loader-traversal-workflow-plan.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_workflow_execution":
            payloads["custom-loader-traversal-workflow-execution.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_loop_plan":
            payloads["custom-loader-traversal-loop-plan.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_loop_execution":
            payloads["custom-loader-traversal-loop-execution.json"] = evidence.details
        elif evidence.source == "custom_loader_recursive_traversal_plan":
            payloads["custom-loader-recursive-traversal-plan.json"] = evidence.details
        elif evidence.source == "custom_loader_recursive_traversal_followup":
            payloads["custom-loader-recursive-traversal-followup.json"] = evidence.details
        elif evidence.source == "custom_loader_recursive_traversal_execution":
            payloads["custom-loader-recursive-traversal-execution.json"] = evidence.details
        elif evidence.source == "custom_loader_continuation_workflow":
            payloads["custom-loader-continuation-workflow.json"] = evidence.details
        elif evidence.source == "custom_loader_continuation_journal":
            payloads["custom-loader-continuation-journal.json"] = evidence.details
        elif evidence.source == "custom_loader_continuation_execution":
            payloads["custom-loader-continuation-execution.json"] = evidence.details
        elif evidence.source == "custom_loader_execution_preflight":
            payloads["custom-loader-execution-preflight.json"] = evidence.details
        elif evidence.source == "custom_loader_execution_result":
            payloads["custom-loader-execution-result.json"] = evidence.details
        elif evidence.source == "custom_loader_module_diff":
            payloads["custom-loader-module-diff.json"] = evidence.details
        elif evidence.source == "module_federation_get_init_plan":
            payloads["module-federation-get-init-plan.json"] = evidence.details
        elif evidence.source == "module_federation_get_init_result":
            payloads["module-federation-get-init-result.json"] = evidence.details
        elif evidence.source == "module_federation_factory_invoke_result":
            payloads["module-federation-factory-invoke-result.json"] = evidence.details
        elif evidence.source == "module_federation_export_hook_plan":
            payloads["module-federation-export-hook-plan.json"] = evidence.details
        elif evidence.source == "module_federation_traversal_graph":
            payloads["module-federation-traversal-graph.json"] = evidence.details
        elif evidence.source == "module_federation_traversal_workflow_plan":
            payloads["module-federation-traversal-workflow-plan.json"] = evidence.details
        elif evidence.source == "module_federation_traversal_workflow_execution":
            payloads["module-federation-traversal-workflow-execution.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_traversal_plan":
            payloads["module-federation-recursive-traversal-plan.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_traversal_followup":
            payloads["module-federation-recursive-traversal-followup.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_traversal_execution":
            payloads["module-federation-recursive-traversal-execution.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_continuation_journal":
            payloads["module-federation-recursive-continuation-journal.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_continuation_checkpoint":
            payloads["module-federation-recursive-continuation-checkpoint.json"] = evidence.details
        elif evidence.source == "recursive_continuation_readiness":
            payloads["recursive-continuation-readiness.json"] = evidence.details
        elif evidence.source == "async_chunk_load_result":
            payloads["async-chunk-load-result.json"] = evidence.details
        elif evidence.source == "source_map_fetch_plan":
            payloads["source-map-fetch-plan.json"] = evidence.details
        elif evidence.source == "source_map_fetch_result":
            payloads["source-map-fetch-result.json"] = evidence.details
        elif evidence.source == "source_map_lookup":
            payloads["source-map-lookup.json"] = evidence.details
        elif evidence.source == "source_map_source_content":
            payloads["source-map-source-content.json"] = evidence.details
        elif evidence.source == "source_map_readiness":
            payloads["source-map-readiness.json"] = evidence.details
        elif evidence.source == "source_map_consumer_action_plan":
            payloads["source-map-consumer-action-plan.json"] = evidence.details
        elif evidence.source == "source_map_consumer_materialization":
            payloads["source-map-consumer-materialization.json"] = evidence.details
        elif evidence.source == "source_map_typed_payload_preflight":
            payloads["source-map-typed-payload-preflight.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_review":
            payloads["source-map-followthrough-review.json"] = evidence.details
        elif evidence.source == "bundler_symbol_scope":
            payloads["bundler-symbol-scope.json"] = evidence.details
        elif evidence.source == "source_logpoints":
            payloads["source-logpoints.json"] = evidence.details
        elif evidence.source == "source_logpoint_timeline":
            payloads["source-logpoint-timeline.json"] = evidence.details
        elif evidence.source == "object_root_mutation_audit":
            payloads["object-root-mutation-audit.json"] = evidence.details
        elif evidence.source == "object_graph_diff":
            payloads["object-graph-diff.json"] = evidence.details
        elif evidence.source == "breakpoint_manager":
            payloads["breakpoints.json"] = evidence.details
        elif evidence.source == "debugger_paused":
            payloads["debugger-paused.json"] = evidence.details
        elif evidence.source == "debugger_callframes":
            payloads["callframes.json"] = evidence.details
        elif evidence.source == "debugger_callframe_evaluations":
            payloads["callframe-evaluations.json"] = evidence.details
        elif evidence.source == "debugger_actions":
            payloads["debugger-actions.json"] = evidence.details
        elif evidence.source == "debugger_session":
            payloads["debugger-session.json"] = evidence.details
        elif evidence.source == "debugger_timeline":
            payloads["debugger-timeline.json"] = evidence.details
        elif evidence.source == "paused_session_live_continuation_preflight":
            payloads["paused-session-live-continuation-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_target_attach_readiness":
            payloads["paused-session-target-attach-readiness.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_execution_plan":
            payloads["paused-session-cross-process-execution-plan.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_session_lifecycle":
            payloads["paused-session-cross-process-session-lifecycle.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_attach_probe":
            payloads["paused-session-cross-process-attach-probe.json"] = evidence.details
        elif evidence.source == "paused_session_live_callframe_recovery":
            payloads["paused-session-live-callframe-recovery.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_one_action_execution":
            payloads["paused-session-cross-process-one-action-execution.json"] = evidence.details
        elif evidence.source == "paused_session_next_paused_event_capture_plan":
            payloads["paused-session-next-paused-event-capture-plan.json"] = evidence.details
        elif evidence.source == "paused_session_next_paused_event_capture_execution":
            payloads["paused-session-next-paused-event-capture-execution.json"] = evidence.details
        elif evidence.source == "paused_session_pre_action_subscribe_and_action":
            payloads["paused-session-pre-action-subscribe-and-action.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_continuation_checkpoint":
            payloads["paused-session-cross-process-continuation-checkpoint.json"] = evidence.details
        elif evidence.source == "paused_session_multi_step_continuation_workflow":
            payloads["paused-session-multi-step-continuation-workflow.json"] = evidence.details
        elif evidence.source == "paused_session_multi_step_continuation_execution":
            payloads["paused-session-multi-step-continuation-execution.json"] = evidence.details
        elif evidence.source == "paused_session_multi_step_loop_plan":
            payloads["paused-session-multi-step-loop-plan.json"] = evidence.details
        elif evidence.source == "paused_session_multi_step_loop_execution":
            payloads["paused-session-multi-step-loop-execution.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_readiness":
            payloads["paused-session-automatic-loop-readiness.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_execution_plan":
            payloads["paused-session-automatic-loop-execution-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_executor_preflight":
            payloads["paused-session-automatic-loop-executor-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_executor_approval_plan":
            payloads["paused-session-automatic-loop-executor-approval-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_executor_approval_record":
            payloads["paused-session-automatic-loop-executor-approval-record.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_transaction_preflight":
            payloads["paused-session-automatic-loop-transaction-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_executor_journal":
            payloads["paused-session-automatic-loop-executor-journal.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_bounded_executor_gate":
            payloads["paused-session-automatic-loop-bounded-executor-gate.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_execution_result":
            payloads["paused-session-automatic-loop-execution-result.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_followup_checkpoint":
            payloads["paused-session-automatic-loop-followup-checkpoint.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_next_iteration_plan":
            payloads["paused-session-automatic-loop-next-iteration-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_next_iteration_execution":
            payloads["paused-session-automatic-loop-next-iteration-execution.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_next_iteration_followup_checkpoint":
            payloads["paused-session-automatic-loop-next-iteration-followup-checkpoint.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_following_iteration_plan":
            payloads["paused-session-automatic-loop-following-iteration-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_policy":
            payloads["paused-session-automatic-loop-multi-iteration-policy.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_executor_preflight":
            payloads["paused-session-automatic-loop-multi-iteration-executor-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_execution_plan":
            payloads["paused-session-automatic-loop-multi-iteration-execution-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_executor_approval_plan":
            payloads["paused-session-automatic-loop-multi-iteration-executor-approval-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_executor_approval_record":
            payloads["paused-session-automatic-loop-multi-iteration-executor-approval-record.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_transaction_preflight":
            payloads["paused-session-automatic-loop-multi-iteration-transaction-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_transaction_journal":
            payloads["paused-session-automatic-loop-multi-iteration-executor-journal.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_bounded_executor_gate":
            payloads["paused-session-automatic-loop-multi-iteration-bounded-executor-gate.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_execution_result":
            payloads["paused-session-automatic-loop-multi-iteration-execution-result.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_followup_checkpoint":
            payloads["paused-session-automatic-loop-multi-iteration-followup-checkpoint.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_next_step_plan":
            payloads["paused-session-automatic-loop-multi-iteration-next-step-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_executor_input_preflight":
            payloads["paused-session-automatic-loop-multi-iteration-executor-input-preflight.json"] = evidence.details
        elif evidence.source == "closure_functions":
            payloads["closure-functions.json"] = evidence.details
        elif evidence.source == "closure_function_candidates":
            payloads["closure-function-candidates.json"] = evidence.details
        elif evidence.source == "closure_wrapper_replacement_plan":
            payloads["closure-wrapper-replacement-plan.json"] = evidence.details
        elif evidence.source == "closure_wrapper_assignment_safety":
            payloads["closure-wrapper-assignment-safety.json"] = evidence.details
        elif evidence.source == "closure_wrapper_runtime_mutability_preflight":
            payloads["closure-wrapper-runtime-mutability-preflight.json"] = evidence.details
        elif evidence.source == "closure_wrapper_runtime_mutability_result":
            payloads["closure-wrapper-runtime-mutability-result.json"] = evidence.details
        elif evidence.source == "closure_wrapper_replacement_execution":
            payloads["closure-wrapper-replacement-execution.json"] = evidence.details
        elif evidence.source == "closure_wrapper_restore_plan":
            payloads["closure-wrapper-restore-plan.json"] = evidence.details
        elif evidence.source == "closure_wrapper_restore_execution":
            payloads["closure-wrapper-restore-execution.json"] = evidence.details
        elif evidence.source == "closure_wrapper_events":
            payloads["closure-wrapper-events.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_readiness":
            payloads["closure-wrapper-continuation-readiness.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_execution_plan":
            payloads["closure-wrapper-continuation-execution-plan.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_execution":
            payloads["closure-wrapper-continuation-execution.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_checkpoint":
            payloads["closure-wrapper-continuation-checkpoint.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_next_iteration_plan":
            payloads["closure-wrapper-continuation-next-iteration-plan.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_next_iteration_execution":
            payloads["closure-wrapper-continuation-next-iteration-execution.json"] = evidence.details
        elif evidence.source == "runtime_context":
            payloads["runtime-context.json"] = evidence.details
        elif evidence.source == "dom_snapshot":
            payloads["dom-snapshot.json"] = evidence.details
        elif evidence.source == "script_inventory":
            payloads["script-inventory.json"] = evidence.details
        elif evidence.source == "console_message":
            payloads["console-messages.json"] = evidence.details
        elif evidence.source == "navigate_page":
            payloads["navigation-events.json"] = evidence.details
        elif evidence.source == "runtime_context_diff":
            payloads["runtime-context-diff.json"] = evidence.details
        elif evidence.source == "function_candidate_card":
            payloads["function-candidates.json"] = evidence.details
        elif evidence.source == "function_validation_result":
            payloads["function-validations.json"] = evidence.details
        elif evidence.source == "function_validation_summary":
            payloads["function-validation-summary.json"] = evidence.details
    return payloads


def _final_from_recon(task_card: TaskCard, route_result: RouterResult, recon_result: ReconResult) -> FinalResult:
    return FinalResult(
        task_card=task_card,
        mode=route_result.selected_mode,
        stage=recon_result.stage,
        status=recon_result.status,
        key_findings=KeyFindings(
            facts=recon_result.key_findings.facts,
            inferences=recon_result.key_findings.inferences,
            unknowns=recon_result.key_findings.unknowns,
        ),
        evidence=recon_result.evidence,
        artifacts=recon_result.artifacts,
        next_action=recon_result.next_action,
        confidence=recon_result.confidence,
    )
