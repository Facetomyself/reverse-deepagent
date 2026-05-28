import unittest

from reverse_deepagent.adapters.platforms import (
    AndroidAdbRuntime,
    IosSimulatorRuntime,
    MiniProgramDevtoolsRuntime,
    PlatformCommandResult,
)
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends
from reverse_deepagent.runtime import ReverseRuntime, WebReverseRuntime


def fake_runner(command: list[str], timeout: float) -> PlatformCommandResult:
    return PlatformCommandResult(
        command=command,
        ok=True,
        returncode=0,
        stdout=f"ok:{' '.join(command)}",
    )


class PlatformRuntimeTests(unittest.TestCase):
    def test_platform_backends_are_registered_without_web_semantics(self) -> None:
        metadata = {item["backend_id"]: item for item in list_runtime_backends()}
        for backend_id, platform in (
            ("android-adb", "android"),
            ("ios-simulator", "ios"),
            ("mini-program-devtools", "mini-program"),
        ):
            self.assertIn(backend_id, metadata)
            item = metadata[backend_id]
            self.assertEqual(item["target_platforms"], [platform])
            self.assertFalse(item["supports_browser_session"])
            self.assertFalse(item["supports_web_recon"])
            self.assertTrue(item["supports_artifact_export"])

    def test_platform_backend_aliases_build_non_web_runtimes(self) -> None:
        for alias in ("adb", "simctl", "mp-devtools"):
            runtime = build_runtime(alias)
            self.assertIsInstance(runtime, ReverseRuntime)
            self.assertNotIsInstance(runtime, WebReverseRuntime)

    def test_android_probe_and_export_bundle_are_normalized(self) -> None:
        runtime = AndroidAdbRuntime(adb_command="adb", device_serial="device-1", command_runner=fake_runner)
        probe = runtime.probe_tools()
        self.assertTrue(probe["available"])
        self.assertEqual(probe["target_platform"], "android")
        self.assertIn(["adb", "version"], [item["command"] for item in probe["probes"]])
        bundle = runtime.export_reverse_artifacts()
        self.assertEqual(bundle.artifacts[0]["metadata"]["target_platform"], "android")
        self.assertEqual(bundle.artifacts[0]["metadata"]["category"], "runtime-context")

    def test_ios_probe_commands_use_simctl(self) -> None:
        runtime = IosSimulatorRuntime(xcrun_command="xcrun", command_runner=fake_runner)
        commands = runtime.probe_commands()
        self.assertIn(["xcrun", "simctl", "list", "devices", "-j"], commands)
        self.assertTrue(runtime.probe_tools()["available"])


    def test_platform_config_summary_redacts_local_selectors(self) -> None:
        runtime = MiniProgramDevtoolsRuntime(
            devtools_command="devtools",
            project_path="/Users/example/private-mini-program",
            command_runner=fake_runner,
        )
        summary = runtime.describe_capabilities().config
        self.assertEqual(summary["project_path"], "<configured>")

    def test_mini_program_unconfigured_command_reports_unavailable(self) -> None:
        runtime = MiniProgramDevtoolsRuntime()
        probe = runtime.probe_tools()
        self.assertFalse(probe["available"])
        self.assertEqual(probe["probes"][0]["unavailable_reason"], "mini-program-devtools-command-not-configured")


if __name__ == "__main__":
    unittest.main()
