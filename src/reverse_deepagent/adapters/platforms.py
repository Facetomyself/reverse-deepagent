from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from pydantic import Field

from reverse_deepagent.runtime.base import ReverseRuntime, RuntimeBackendCapabilities, RuntimeExportBundle
from reverse_deepagent.schemas import (
    ArtifactKind,
    ArtifactRef,
    ConfidenceLevel,
    ExecutionStatus,
    ProtectionResult,
    SchemaBaseModel,
)
from reverse_deepagent.schemas.final_result import FinalResult


class PlatformCommandResult(SchemaBaseModel):
    """Normalized result from a local platform tooling probe."""

    command: list[str] = Field(description="Command argv that was attempted.")
    ok: bool = Field(description="Whether the command completed successfully.")
    returncode: int | None = Field(default=None, description="Process return code, or None when not started.")
    stdout: str = Field(default="", description="Captured stdout.")
    stderr: str = Field(default="", description="Captured stderr.")
    unavailable_reason: str | None = Field(default=None, description="Why the command could not run, if applicable.")


PlatformCommandRunner = Callable[[list[str], float], PlatformCommandResult]


class PlatformRuntimeConfig(SchemaBaseModel):
    """Serializable config shared by non-Web platform runtimes."""

    backend_id: str = Field(description="Stable backend id.")
    display_name: str = Field(description="Human-readable backend name.")
    transport: str = Field(description="Runtime transport, such as adb, xcrun-simctl, or vendor-devtools-cli.")
    target_platform: str = Field(description="Target platform, such as android, ios, or mini-program.")
    primary_command: str | None = Field(default=None, description="Primary local tooling command.")
    secondary_command: str | None = Field(default=None, description="Optional secondary local tooling command.")
    package_name: str | None = Field(default=None, description="Optional Android package name; safe summary only.")
    bundle_id: str | None = Field(default=None, description="Optional iOS bundle id; safe summary only.")
    project_path: str | None = Field(default=None, description="Optional mini-program project path; local path only.")
    vendor: str | None = Field(default=None, description="Mini-program vendor, such as wechat or alipay.")
    device_selector: str | None = Field(default=None, description="Optional redacted device/simulator selector.")
    request_timeout: float = Field(default=10.0, description="Timeout for side-effect-light local probes.")
    artifact_sample_limit: int = Field(default=50, description="Maximum raw lines/items retained in future artifacts.")

    def safe_summary(self) -> dict[str, Any]:
        """Return metadata safe for public manifests and capability listing."""

        payload = self.model_dump(mode="json")
        for sensitive_key in ("device_selector", "project_path"):
            if payload.get(sensitive_key):
                payload[sensitive_key] = "<configured>"
        return payload


class PlatformRuntimeBase(ReverseRuntime):
    """Base class for platform-neutral runtimes backed by local toolchains."""

    config: PlatformRuntimeConfig

    def __init__(self, config: PlatformRuntimeConfig, command_runner: PlatformCommandRunner | None = None) -> None:
        self.config = config
        self._command_runner = command_runner or run_platform_command

    def describe_capabilities(self) -> RuntimeBackendCapabilities:
        return RuntimeBackendCapabilities(
            backend_id=self.config.backend_id,
            display_name=self.config.display_name,
            transport=self.config.transport,
            target_platforms=[self.config.target_platform],
            supports_browser_session=False,
            supports_web_recon=False,
            supports_protection_patch=True,
            supports_artifact_export=True,
            supports_runtime_context=True,
            supports_replay_validation=False,
            managed_chrome=False,
            mcp_backed=False,
            evidence_kinds=["static", "dynamic", "hook", "storage", "network", "note"],
            artifact_kinds=["json", "export", "runtime-context", "trace", "static-analysis"],
            notes=[
                "platform-neutral non-Web runtime backend",
                "metadata listing is side-effect free; tool probes run only after explicit runtime construction",
            ],
            config=self.config.safe_summary(),
        )

    def probe_tools(self) -> dict[str, Any]:
        """Run side-effect-light local tooling probes for this backend."""

        probes = [self._run_probe(command) for command in self.probe_commands()]
        return {
            "backend_id": self.config.backend_id,
            "target_platform": self.config.target_platform,
            "transport": self.config.transport,
            "available": any(item.ok for item in probes),
            "probes": [item.model_dump(mode="json") for item in probes],
        }

    def probe_commands(self) -> list[list[str]]:
        """Return argv probes. Subclasses override with platform-specific commands."""

        return []

    def apply_minimal_protection(self, protection_name: str, context: dict[str, Any] | None = None) -> ProtectionResult:
        context = context or {}
        probe = self.probe_tools()
        status = ExecutionStatus.PARTIAL if probe["available"] else ExecutionStatus.FAILED
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=[],
            verification=[
                "Non-Web platform protection is routed through platform-specific tooling; no generic patch was applied.",
                f"toolchain_available={probe['available']}",
            ],
            status=status,
            artifacts=[
                ArtifactRef(
                    path=f"virtual://platform/{self.config.backend_id}/tool-probe.json",
                    kind=ArtifactKind.EXPORT,
                    description="Platform runtime toolchain probe used to decide whether protection can proceed.",
                    metadata={"backend_id": self.config.backend_id, "context_keys": sorted(context)},
                )
            ],
            next_action="run_platform_specific_protection" if probe["available"] else "install_or_configure_platform_tooling",
            confidence=ConfidenceLevel.MEDIUM if probe["available"] else ConfidenceLevel.LOW,
        )

    def export_reverse_artifacts(self, final_result: FinalResult | None = None) -> RuntimeExportBundle:
        probe = self.probe_tools()
        artifact = ArtifactRef(
            path=f"virtual://platform/{self.config.backend_id}/tool-probe.json",
            kind=ArtifactKind.EXPORT,
            description="Side-effect-light platform toolchain probe summary.",
            metadata={
                "backend_id": self.config.backend_id,
                "target_platform": self.config.target_platform,
                "transport": self.config.transport,
                "available": probe["available"],
                "category": "runtime-context",
            },
        )
        return RuntimeExportBundle(
            final_result=final_result,
            exports=[{"tool": "platform_tool_probe", "payload": probe}],
            artifacts=[artifact.model_dump(mode="json")],
        )

    def _run_probe(self, command: list[str]) -> PlatformCommandResult:
        return self._command_runner(command, self.config.request_timeout)


class AndroidAdbRuntime(PlatformRuntimeBase):
    """Android backend using local ADB for device/app discovery probes."""

    def __init__(
        self,
        *,
        adb_command: str = "adb",
        device_serial: str | None = None,
        package_name: str | None = None,
        request_timeout: float = 10.0,
        command_runner: PlatformCommandRunner | None = None,
    ) -> None:
        config = PlatformRuntimeConfig(
            backend_id="android-adb",
            display_name="Android ADB Runtime",
            transport="adb",
            target_platform="android",
            primary_command=adb_command,
            package_name=package_name,
            device_selector=device_serial,
            request_timeout=request_timeout,
        )
        super().__init__(config, command_runner=command_runner)

    def probe_commands(self) -> list[list[str]]:
        adb = self.config.primary_command or "adb"
        commands = [[adb, "version"], [adb, "devices", "-l"]]
        if self.config.device_selector:
            commands.append([adb, "-s", self.config.device_selector, "shell", "getprop", "ro.build.version.sdk"])
        return commands


class IosSimulatorRuntime(PlatformRuntimeBase):
    """iOS backend using xcrun simctl for simulator discovery probes."""

    def __init__(
        self,
        *,
        xcrun_command: str = "xcrun",
        device_id: str | None = None,
        bundle_id: str | None = None,
        request_timeout: float = 10.0,
        command_runner: PlatformCommandRunner | None = None,
    ) -> None:
        config = PlatformRuntimeConfig(
            backend_id="ios-simulator",
            display_name="iOS Simulator Runtime",
            transport="xcrun-simctl",
            target_platform="ios",
            primary_command=xcrun_command,
            bundle_id=bundle_id,
            device_selector=device_id,
            request_timeout=request_timeout,
        )
        super().__init__(config, command_runner=command_runner)

    def probe_commands(self) -> list[list[str]]:
        xcrun = self.config.primary_command or "xcrun"
        return [[xcrun, "simctl", "help"], [xcrun, "simctl", "list", "devices", "-j"]]


class MiniProgramDevtoolsRuntime(PlatformRuntimeBase):
    """Mini-program backend using an optional vendor developer-tools CLI."""

    def __init__(
        self,
        *,
        devtools_command: str | None = None,
        vendor: str = "wechat",
        project_path: str | None = None,
        request_timeout: float = 10.0,
        command_runner: PlatformCommandRunner | None = None,
    ) -> None:
        config = PlatformRuntimeConfig(
            backend_id="mini-program-devtools",
            display_name="Mini-program Developer Tools Runtime",
            transport="vendor-devtools-cli",
            target_platform="mini-program",
            primary_command=devtools_command,
            project_path=project_path,
            vendor=vendor,
            request_timeout=request_timeout,
        )
        super().__init__(config, command_runner=command_runner)

    def probe_commands(self) -> list[list[str]]:
        if not self.config.primary_command:
            return [["<mini-program-devtools-command-not-configured>"]]
        return [[self.config.primary_command, "--version"]]


def run_platform_command(command: list[str], timeout: float) -> PlatformCommandResult:
    """Run a local platform command with safe unavailable handling."""

    if not command:
        return PlatformCommandResult(command=command, ok=False, unavailable_reason="empty command")
    executable = command[0]
    if executable.startswith("<") and executable.endswith(">"):
        return PlatformCommandResult(command=command, ok=False, unavailable_reason=executable.strip("<>"))
    if shutil.which(executable) is None:
        return PlatformCommandResult(command=command, ok=False, unavailable_reason=f"command not found: {executable}")
    try:
        proc = subprocess.run(  # noqa: S603 - explicit local tooling command configured by user/runtime.
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return PlatformCommandResult(
            command=command,
            ok=False,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            unavailable_reason=f"timeout after {timeout}s",
        )
    except OSError as exc:
        return PlatformCommandResult(command=command, ok=False, unavailable_reason=str(exc))
    return PlatformCommandResult(
        command=command,
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
