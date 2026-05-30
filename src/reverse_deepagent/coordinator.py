from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
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
from reverse_deepagent.workspace_contract import workspace_contract_payload

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
) -> dict[str, str]:
    """Persist the standard workspace/report/export artifact set."""

    workspace_dir = base_dir / "workspace"
    reports_dir = base_dir / "reports"
    exports_dir = base_dir / "exports"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    task_card_path = workspace_dir / "task-card.json"
    route_path = workspace_dir / "route-decision.json"
    recon_path = workspace_dir / "recon-result.json"
    final_workspace_path = workspace_dir / "final-result.json"
    workspace_contract_path = workspace_dir / "workspace-contract.json"
    report_json_path = reports_dir / "demo-final-result.json"
    report_md_path = reports_dir / "demo-final-report.md"
    manifest_path = workspace_dir / "backend-artifact-manifest.json"
    index_path = exports_dir / "artifact-index.json"
    workspace_artifact_paths = _write_workspace_artifacts(workspace_dir, final_result)
    rebuild_result = write_rebuild_bundle(base_dir, task_card, final_result)
    rebuild_artifact_paths = _rebuild_paths_from_result(rebuild_result)

    _write_json(task_card_path, task_card.model_dump(mode="json"))
    _write_json(route_path, route_result.model_dump(mode="json"))
    _write_json(recon_path, recon_result.model_dump(mode="json"))
    _write_json(final_workspace_path, final_result.model_dump(mode="json"))
    _write_json(workspace_contract_path, workspace_contract_payload())
    evidence_promotion = promote_evidence(final_result.evidence, final_result.artifacts)
    evidence_artifact_paths = _write_evidence_promotion_artifacts(workspace_dir, evidence_promotion)
    review_gate = evaluate_review_gate(rebuild_result, evidence_promotion)
    review_gate_path = _write_review_gate_artifact(workspace_dir, review_gate)
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
    output_paths["workspace_backend_artifact_manifest"] = str(manifest_path)

    capabilities = runtime_capabilities or RuntimeBackendCapabilities(backend_id="unknown", display_name="Unknown Runtime")
    runtime_artifacts = export_bundle.get("artifacts", []) if isinstance(export_bundle, dict) else []
    backend_artifact_manifest = _build_backend_artifact_manifest(capabilities, output_paths, extra_artifacts=runtime_artifacts)
    _write_json(manifest_path, backend_artifact_manifest.model_dump(mode="json"))

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
            metadata=_artifact_manifest_entry_metadata(capabilities, path),
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
    "workspace_source_logpoints": "trace",
    "workspace_source_logpoint_timeline": "trace",
    "workspace_mutation_audit": "trace",
    "workspace_page_mutation_audit": "trace",
    "workspace_mutation_observer_timeline": "trace",
    "workspace_breakpoints": "trace",
    "workspace_debugger_paused": "trace",
    "workspace_callframes": "trace",
    "workspace_callframe_evaluations": "trace",
    "workspace_debugger_actions": "trace",
    "workspace_debugger_session": "trace",
    "workspace_debugger_timeline": "trace",
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
    "workspace_review_gate_after_rollback": "triage",
    "workspace_review_gate": "triage",
}


def _artifact_manifest_entry_metadata(capabilities: RuntimeBackendCapabilities, path: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"path_style": "virtual" if path.startswith("virtual://") else "filesystem"}
    provider = capabilities.config.get("provider") if isinstance(capabilities.config, dict) else None
    if isinstance(provider, dict):
        provider_id = provider.get("provider_id")
        if provider_id:
            metadata["browser_provider"] = provider_id
        provider_transport = provider.get("transport")
        if provider_transport:
            metadata["browser_provider_transport"] = provider_transport
    return metadata


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
) -> dict[str, str]:
    """Persist the platform-neutral workspace/report/export artifact set."""

    workspace_dir = base_dir / "workspace"
    reports_dir = base_dir / "reports"
    exports_dir = base_dir / "exports"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    task_card_path = workspace_dir / "task-card.json"
    route_path = workspace_dir / "route-decision.json"
    capabilities_path = workspace_dir / "runtime-capabilities.json"
    export_bundle_path = workspace_dir / "runtime-export-bundle.json"
    final_workspace_path = workspace_dir / "final-result.json"
    workspace_contract_path = workspace_dir / "workspace-contract.json"
    manifest_path = workspace_dir / "backend-artifact-manifest.json"
    report_json_path = reports_dir / "platform-pipeline-result.json"
    report_md_path = reports_dir / "platform-pipeline-report.md"
    index_path = exports_dir / "artifact-index.json"

    export_payload = export_bundle.model_dump(mode="json")
    _write_json(task_card_path, task_card.model_dump(mode="json"))
    _write_json(route_path, route_result.model_dump(mode="json"))
    _write_json(capabilities_path, runtime_capabilities.model_dump(mode="json"))
    _write_json(export_bundle_path, export_payload)
    _write_json(final_workspace_path, final_result.model_dump(mode="json"))
    _write_json(workspace_contract_path, workspace_contract_payload())
    evidence_promotion = promote_evidence(final_result.evidence, final_result.artifacts)
    evidence_artifact_paths = _write_evidence_promotion_artifacts(workspace_dir, evidence_promotion)
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
        "workspace_backend_artifact_manifest": str(manifest_path),
    }
    output_paths.update({f"workspace_{key}": value for key, value in evidence_artifact_paths.items()})
    platform_probe_path = _write_platform_tool_probe_if_present(workspace_dir, export_bundle)
    if platform_probe_path is not None:
        output_paths["workspace_platform_tool_probe"] = str(platform_probe_path)

    manifest = _build_backend_artifact_manifest(
        runtime_capabilities,
        output_paths,
        extra_artifacts=export_payload.get("artifacts", []),
    )
    _write_json(manifest_path, manifest.model_dump(mode="json"))
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
    _write_json(index_path, artifact_index)
    return output_paths


def _write_platform_tool_probe_if_present(workspace_dir: Path, export_bundle: RuntimeExportBundle) -> Path | None:
    for item in export_bundle.exports:
        if not isinstance(item, dict):
            continue
        if item.get("tool") != "platform_tool_probe":
            continue
        path = workspace_dir / "platform-tool-probe.json"
        _write_json(path, item.get("payload", {}))
        return path
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_evidence_promotion_artifacts(workspace_dir: Path, evidence_promotion: Any) -> dict[str, str]:
    paths: dict[str, str] = {}
    for filename, payload in promotion_workspace_payloads(evidence_promotion).items():
        path = workspace_dir / filename
        _write_json(path, payload)
        paths[filename.removesuffix(".json").replace("-", "_")] = str(path)
    return paths


def _write_review_gate_artifact(workspace_dir: Path, review_gate: Any) -> Path:
    path = workspace_dir / "review-gate.json"
    _write_json(path, review_gate_workspace_payload(review_gate))
    return path


def _write_workspace_artifacts(workspace_dir: Path, final_result: FinalResult) -> dict[str, str]:
    payloads = _extract_workspace_artifact_payloads(final_result)
    paths: dict[str, str] = {}
    for filename, payload in payloads.items():
        path = workspace_dir / filename
        _write_json(path, payload)
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
        elif evidence.source == "source_logpoints":
            payloads["source-logpoints.json"] = evidence.details
        elif evidence.source == "source_logpoint_timeline":
            payloads["source-logpoint-timeline.json"] = evidence.details
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
