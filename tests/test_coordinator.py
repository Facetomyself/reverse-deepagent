import tempfile
import unittest
import json
from pathlib import Path

from reverse_deepagent.coordinator import (
    _artifact_category_from_key,
    _extract_workspace_artifact_payloads,
    build_runtime,
    legacy_mcp_alias_warning,
    list_runtime_backends,
    run_reverse_pipeline,
)
from reverse_deepagent.runtime import ReverseRuntime, RuntimeExportBundle
from reverse_deepagent.schemas import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceKind,
    ExecutionStatus,
    FinalResult,
    KeyFindings,
    ProtectionResult,
    ReverseMode,
    ReverseStage,
    TaskCard,
)


class NonWebRuntime(ReverseRuntime):
    def apply_minimal_protection(self, protection_name: str, context: dict | None = None) -> ProtectionResult:
        raise NotImplementedError

    def export_reverse_artifacts(self, final_result=None) -> RuntimeExportBundle:
        return RuntimeExportBundle(final_result=final_result)


class CoordinatorTests(unittest.TestCase):
    def test_build_runtime_exposes_mock_capabilities(self) -> None:
        runtime = build_runtime("mock")
        capabilities = runtime.describe_capabilities()
        self.assertEqual(capabilities.backend_id, "mock")
        self.assertEqual(capabilities.transport, "in-process")
        self.assertTrue(capabilities.supports_web_recon)
        self.assertFalse(capabilities.mcp_backed)

    def test_runtime_backend_metadata_lists_mock_and_legacy_mcp(self) -> None:
        metadata = list_runtime_backends()
        by_id = {item["backend_id"]: item for item in metadata}
        self.assertIn("mock", by_id)
        self.assertIn("legacy-mcp", by_id)
        self.assertNotIn("mcp", by_id)
        self.assertEqual(by_id["legacy-mcp"]["transport"], "mcp-stdio")
        self.assertTrue(by_id["legacy-mcp"]["mcp_backed"])
        self.assertIn("mcp", by_id["legacy-mcp"]["config"]["aliases"])

    def test_workspace_artifact_payloads_include_breakpoint_manager(self) -> None:
        final_result = FinalResult(
            task_card=TaskCard(
                target_url_or_file="https://example.test",
                target_param_or_api="sign",
                goal="set breakpoint",
                boundaries="unit test",
            ),
            mode=ReverseMode.DEBUG_BLOCKED,
            stage=ReverseStage.BREAKPOINT,
            status=ExecutionStatus.SUCCESS,
            key_findings=KeyFindings(),
            evidence=[
                EvidenceItem(
                    summary="Native breakpoint manager result",
                    kind=EvidenceKind.CALLSTACK,
                    source="breakpoint_manager",
                    details={"status": "success", "count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native debugger callframe evaluations",
                    kind=EvidenceKind.CALLSTACK,
                    source="debugger_callframe_evaluations",
                    details={"evaluations": [{"expression": "typeof buildSign", "ok": True, "value": "function"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                )
            ],
            artifacts=[],
            next_action="wait_for_breakpoint",
            confidence=ConfidenceLevel.MEDIUM,
        )
        payloads = _extract_workspace_artifact_payloads(final_result)
        self.assertEqual(payloads["breakpoints.json"], {"status": "success", "count": 1})
        self.assertEqual(payloads["callframe-evaluations.json"]["evaluations"][0]["value"], "function")
        self.assertEqual(_artifact_category_from_key("workspace_breakpoints"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_callframe_evaluations"), "trace")

    def test_build_runtime_threads_legacy_mcp_config_summary_and_alias(self) -> None:
        runtime = build_runtime(
            "legacy-mcp",
            browser_url="http://127.0.0.1:9555",
            mcp_command="/tmp/jsreverser-mcp",
        )
        try:
            capabilities = runtime.describe_capabilities()
            self.assertEqual(capabilities.backend_id, "legacy-mcp")
            self.assertEqual(capabilities.config["command"], "/tmp/jsreverser-mcp")
            self.assertEqual(capabilities.config["browser_url"], "http://127.0.0.1:9555")
        finally:
            runtime.close()

        alias_runtime = build_runtime("mcp", browser_url="http://127.0.0.1:9555", mcp_command="/tmp/jsreverser-mcp")
        try:
            self.assertEqual(alias_runtime.describe_capabilities().backend_id, "legacy-mcp")
        finally:
            alias_runtime.close()

    def test_legacy_mcp_alias_warning_only_targets_deprecated_aliases(self) -> None:
        self.assertIsNone(legacy_mcp_alias_warning("legacy-mcp"))
        self.assertIsNone(legacy_mcp_alias_warning("native-web"))
        self.assertIn("legacy-mcp", legacy_mcp_alias_warning("mcp") or "")
        self.assertIn("legacy-mcp", legacy_mcp_alias_warning("jsreverser-mcp") or "")

    def test_web_pipeline_rejects_platform_neutral_non_web_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(TypeError, "does not implement WebReverseRuntime"):
                run_reverse_pipeline(
                    task_text="android://demo 找 sign",
                    artifact_root=Path(tmpdir) / "artifacts",
                    runtime_kind="mock",
                    runtime=NonWebRuntime(),
                )

    def test_run_reverse_pipeline_returns_structured_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign 入口，并给出下一步建议",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="mock",
            )
            self.assertEqual(output.final_result.status.value, "success")
            self.assertIn("workspace_task_card", output.artifacts)
            self.assertIn("workspace_function_candidates", output.artifacts)
            self.assertIn("workspace_function_validations", output.artifacts)
            self.assertIn("workspace_function_validation_summary", output.artifacts)
            self.assertIn("workspace_backend_artifact_manifest", output.artifacts)
            self.assertIn("workspace_rebuild_plan", output.artifacts)
            self.assertIn("rebuild_sign_rebuild", output.artifacts)
            self.assertIn("rebuild_replay_demo", output.artifacts)
            self.assertIn("rebuild_scrapy_middleware", output.artifacts)
            self.assertIn("rebuild_scrapy_export_manifest", output.artifacts)
            self.assertIn("rebuild_scrapy_project", output.artifacts)
            self.assertTrue(Path(output.artifacts["workspace_function_candidates"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_function_validations"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_function_validation_summary"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_backend_artifact_manifest"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_rebuild_plan"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_sign_rebuild"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_replay_demo"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_scrapy_middleware"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_scrapy_export_manifest"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_scrapy_project"]).is_dir())
            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["producer_backend_id"], "mock")
            self.assertEqual(manifest["producer_transport"], "in-process")
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            manifest_keys = set(manifest_by_key)
            manifest_paths = {item["path"] for item in manifest["entries"]}
            self.assertIn("workspace_task_card", manifest_keys)
            self.assertIn("workspace_backend_artifact_manifest", manifest_keys)
            self.assertIn("rebuild_sign_rebuild", manifest_keys)
            self.assertIn("rebuild_scrapy_export_manifest", manifest_keys)
            self.assertIn("rebuild_scrapy_project", manifest_keys)
            self.assertIn("virtual://exports/session-report.json", manifest_paths)
            self.assertEqual(manifest_by_key["workspace_network_requests"]["category"], "network")
            self.assertEqual(manifest_by_key["workspace_source_contexts"]["category"], "source")
            self.assertEqual(manifest_by_key["workspace_function_validations"]["category"], "trace")
            self.assertEqual(manifest_by_key["rebuild_sign_rebuild"]["category"], "rebuild")
            self.assertEqual(manifest_by_key["rebuild_scrapy_export_manifest"]["kind"], "json")
            self.assertEqual(manifest_by_key["rebuild_scrapy_project"]["category"], "rebuild")
            self.assertIsNone(output.chrome_launch)
            self.assertIsNone(output.chrome_stop)


if __name__ == "__main__":
    unittest.main()
