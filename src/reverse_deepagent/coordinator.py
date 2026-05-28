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
from reverse_deepagent.adapters.jsreverser import (
    DEFAULT_JSREVERSER_MCP_COMMAND,
    JSReverserMcpConfig,
    JSReverserRuntime,
    create_jsreverser_mcp_runtime,
)
from reverse_deepagent.rebuild import write_rebuild_bundle
from reverse_deepagent.runtime import RuntimeBackendCapabilities, RuntimeBackendRegistration, RuntimeBackendRegistry, ReverseRuntime, WebReverseRuntime
from reverse_deepagent.runtime import RuntimeArtifactManifest, RuntimeArtifactManifestEntry
from reverse_deepagent.runtime.chrome import ChromeCommandResult, ChromeDebugConfig, ensure_chrome_debug, stop_chrome_debug
from reverse_deepagent.schemas import FinalResult, KeyFindings, ReconResult, RouterResult, SchemaBaseModel, TaskCard
from reverse_deepagent.tools.route_tools import normalize_task_card, route_from_task_card


class ReversePipelineOutput(SchemaBaseModel):
    """Complete result returned by the deterministic coordinator pipeline."""

    final_result: FinalResult = Field(description="Final structured reverse result.")
    artifacts: dict[str, str] = Field(default_factory=dict, description="Generated artifact path index.")
    chrome_launch: ChromeCommandResult | None = Field(default=None, description="Chrome launch command result, if used.")
    chrome_stop: ChromeCommandResult | None = Field(default=None, description="Chrome stop command result, if used.")


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
            return [
                {"id": 101, "url": urljoin(self.active_url.rstrip("/") + "/", "api/search"), "method": "POST"},
                {"id": 102, "url": urljoin(self.active_url.rstrip("/") + "/", "app.js"), "method": "GET"},
            ]
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
        if profile == "sha256":
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if profile == "base64":
            return base64.b64encode(raw.encode("utf-8")).decode("ascii")
        if profile == "context-localstorage":
            return base64.b64encode(f"{raw}:fixture-device".encode("utf-8")).decode("ascii")
        if profile == "context-cookie":
            return base64.b64encode(f"{raw}:fixture-cookie-device".encode("utf-8")).decode("ascii")
        if profile == "context-navigator":
            return hashlib.sha256(f"{raw}:ReverseDeepAgentMock/1.0".encode("utf-8")).hexdigest()
        return f"sig_{keyword}_{timestamp}"

    def _storage_payload(self) -> dict[str, Any]:
        profile = self._profile()
        return {
            "localStorage": {"device_id": "fixture-device"} if profile == "context-localstorage" else {},
            "sessionStorage": {},
            "cookies": {"device_id": "fixture-cookie-device"} if profile == "context-cookie" else {},
        }

    def _runtime_environment(self) -> dict[str, Any]:
        profile = self._profile()
        return {
            "cookie": "device_id=fixture-cookie-device" if profile == "context-cookie" else "",
            "localStorage": {"device_id": "fixture-device"} if profile == "context-localstorage" else {},
            "sessionStorage": {},
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


def _mcp_runtime_factory(
    *,
    browser_url: str | None = None,
    mcp_command: str | None = None,
    **_: Any,
) -> JSReverserRuntime:
    config = JSReverserMcpConfig(
        command=mcp_command or DEFAULT_JSREVERSER_MCP_COMMAND,
        browser_url=browser_url or "http://127.0.0.1:9222",
        backend_id="mcp",
        display_name="JSReverser MCP",
        transport="mcp-stdio",
    )
    return create_jsreverser_mcp_runtime(
        config=config,
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


def build_default_runtime_registry() -> RuntimeBackendRegistry:
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
            backend_id="mcp",
            aliases=("jsreverser-mcp",),
            factory=_mcp_runtime_factory,
            capabilities=RuntimeBackendCapabilities(
                backend_id="mcp",
                display_name="JSReverser MCP",
                transport="mcp-stdio",
                target_platforms=["web"],
                supports_browser_session=True,
                supports_web_recon=True,
                supports_protection_patch=True,
                supports_artifact_export=True,
                supports_runtime_context=True,
                supports_replay_validation=True,
                managed_chrome=True,
                mcp_backed=True,
                evidence_kinds=["request", "callstack", "static", "dynamic", "storage", "note"],
                artifact_kinds=["json", "export", "rebuild", "markdown"],
                notes=["requires jsreverser-mcp and a reachable Chrome DevTools endpoint"],
                config={"default_command": DEFAULT_JSREVERSER_MCP_COMMAND},
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

    return DEFAULT_RUNTIME_BACKEND_REGISTRY.create(
        runtime_kind,
        browser_url=browser_url,
        mcp_command=mcp_command,
        **runtime_kwargs,
    )


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
    _write_json(report_json_path, final_result.model_dump(mode="json"))
    report_md_path.write_text(build_markdown_report(final_result), encoding="utf-8")

    output_paths = {
        "workspace_task_card": str(task_card_path),
        "workspace_route": str(route_path),
        "workspace_recon": str(recon_path),
        "workspace_final": str(final_workspace_path),
        "json": str(report_json_path),
        "markdown": str(report_md_path),
        "index": str(index_path),
    }
    output_paths.update({f"workspace_{key}": value for key, value in workspace_artifact_paths.items()})
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
        },
        "reports": {
            "json": str(report_json_path),
            "markdown": str(report_md_path),
        },
        "runtime_exports": export_bundle,
        "workspace_artifacts": workspace_artifact_paths,
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
            metadata={"path_style": "virtual" if path.startswith("virtual://") else "filesystem"},
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
    "workspace_request_initiators": "trace",
    "workspace_runtime_context": "runtime-context",
    "workspace_runtime_context_diff": "runtime-context",
    "workspace_function_candidates": "source",
    "workspace_function_validations": "trace",
    "workspace_function_validation_summary": "trace",
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


def run_reverse_pipeline(
    task_text: str,
    artifact_root: Path,
    runtime_kind: str = "mock",
    chrome_config: ChromeDebugConfig | None = None,
    ensure_chrome: bool = False,
    keep_chrome: bool = False,
    mcp_command: str | None = None,
    runtime: WebReverseRuntime | None = None,
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
    if runtime_kind == "mcp" and ensure_chrome:
        chrome_launch = ensure_chrome_debug(chrome_config)
        if not chrome_launch.ok:
            raise RuntimeError(f"Failed to ensure Chrome debug session: {chrome_launch.stderr or chrome_launch.stdout}")
        should_stop_chrome = not keep_chrome

    owns_runtime = runtime is None
    active_runtime = runtime or build_runtime(
        runtime_kind,
        browser_url=chrome_config.browser_url if chrome_config else None,
        mcp_command=mcp_command,
    )
    if not isinstance(active_runtime, WebReverseRuntime):
        capabilities = active_runtime.describe_capabilities()
        raise TypeError(
            f"Runtime backend {capabilities.backend_id!r} does not implement WebReverseRuntime; "
            "run_reverse_pipeline is the Web pipeline entrypoint."
        )
    runtime_capabilities = active_runtime.describe_capabilities()
    try:
        recon_result = active_runtime.run_web_recon(task_card=task_card, route_result=route_result)
        final_result = _final_from_recon(task_card, route_result, recon_result)
        export_bundle = active_runtime.export_reverse_artifacts(final_result=final_result).model_dump(mode="json")
    finally:
        if owns_runtime and runtime_kind == "mcp":
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


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        elif evidence.source == "runtime_context":
            payloads["runtime-context.json"] = evidence.details
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
