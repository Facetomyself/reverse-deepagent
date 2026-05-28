import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.adapters.platforms import AndroidAdbRuntime, MiniProgramDevtoolsRuntime, PlatformCommandResult
from reverse_deepagent.cli import main_platform
from reverse_deepagent.coordinator import run_platform_pipeline
from reverse_deepagent.runtime import ReverseRuntime, RuntimeExportBundle
from reverse_deepagent.schemas import ArtifactKind, ProtectionResult


def fake_runner(command: list[str], timeout: float) -> PlatformCommandResult:
    return PlatformCommandResult(
        command=command,
        ok=True,
        returncode=0,
        stdout=f"ok:{' '.join(command)}",
    )


class ExportOnlyRuntime(ReverseRuntime):
    def apply_minimal_protection(self, protection_name: str, context: dict | None = None) -> ProtectionResult:
        raise NotImplementedError

    def export_reverse_artifacts(self, final_result=None) -> RuntimeExportBundle:
        return RuntimeExportBundle(
            final_result=final_result,
            exports=[{"tool": "export_only", "payload": {"ok": True}}],
            artifacts=[
                {
                    "artifact_key": "runtime_export_only",
                    "path": "virtual://exports/export-only.json",
                    "kind": ArtifactKind.EXPORT.value,
                    "description": "Generic platform-neutral export-only artifact.",
                    "metadata": {"category": "export"},
                }
            ],
        )


class PlatformPipelineTests(unittest.TestCase):
    def test_android_platform_pipeline_writes_manifest_and_probe(self) -> None:
        probe_commands: list[list[str]] = []

        def counting_runner(command: list[str], timeout: float) -> PlatformCommandResult:
            probe_commands.append(command)
            return fake_runner(command, timeout)

        runtime = AndroidAdbRuntime(adb_command="adb", device_serial="device-1", command_runner=counting_runner)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_platform_pipeline(
                task_text="android://demo 找 sign 入口，并给出平台下一步建议",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="android-adb",
                runtime=runtime,
            )
            self.assertEqual(output.final_result.status.value, "success")
            self.assertEqual(output.runtime_capabilities.backend_id, "android-adb")
            self.assertIn("workspace_runtime_capabilities", output.artifacts)
            self.assertIn("workspace_runtime_export_bundle", output.artifacts)
            self.assertIn("workspace_platform_tool_probe", output.artifacts)
            self.assertIn("workspace_backend_artifact_manifest", output.artifacts)
            self.assertEqual(len(probe_commands), 3)
            self.assertTrue(Path(output.artifacts["workspace_platform_tool_probe"]).exists())
            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            manifest_paths = {item["path"] for item in manifest["entries"]}
            self.assertEqual(manifest["producer_backend_id"], "android-adb")
            self.assertEqual(manifest["target_platforms"], ["android"])
            self.assertEqual(manifest_by_key["workspace_runtime_capabilities"]["category"], "runtime-context")
            self.assertEqual(manifest_by_key["workspace_platform_tool_probe"]["category"], "runtime-context")
            self.assertIn("virtual://platform/android-adb/tool-probe.json", manifest_paths)
            self.assertIn(
                "The platform-neutral pipeline completed without invoking Web-only browser recon methods.",
                output.final_result.key_findings.inferences,
            )

    def test_unavailable_mini_program_pipeline_is_structured_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_platform_pipeline(
                task_text="mini-program://demo 找 sign",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="mini-program-devtools",
                runtime=MiniProgramDevtoolsRuntime(),
            )
            self.assertEqual(output.final_result.status.value, "partial")
            self.assertEqual(output.final_result.next_action, "install_or_configure_platform_tooling")
            probe = json.loads(Path(output.artifacts["workspace_platform_tool_probe"]).read_text(encoding="utf-8"))
            self.assertFalse(probe["available"])
            self.assertEqual(probe["probes"][0]["unavailable_reason"], "mini-program-devtools-command-not-configured")

    def test_platform_pipeline_accepts_generic_reverse_runtime_without_web_recon(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_platform_pipeline(
                task_text="file://sample.bundle 找 token",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="export-only",
                runtime=ExportOnlyRuntime(),
            )
            self.assertEqual(output.final_result.status.value, "success")
            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            self.assertIn("virtual://exports/export-only.json", {item["path"] for item in manifest["entries"]})
            self.assertIn("runtime_export_only", manifest_by_key)
            self.assertEqual(output.final_result.artifacts[0].path, "virtual://exports/export-only.json")

    def test_platform_cli_writes_json_output_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main_platform(
                    [
                        "--runtime",
                        "mini-program-devtools",
                        "--task-text",
                        "mini-program://demo 找 sign",
                        "--artifact-root",
                        str(Path(tmpdir) / "artifacts"),
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["runtime_capabilities"]["backend_id"], "mini-program-devtools")
            self.assertTrue(Path(payload["artifacts"]["workspace_backend_artifact_manifest"]).exists())


if __name__ == "__main__":
    unittest.main()
