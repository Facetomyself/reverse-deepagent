import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.coordinator import build_runtime, list_runtime_backends, run_reverse_pipeline


class CoordinatorTests(unittest.TestCase):
    def test_build_runtime_exposes_mock_capabilities(self) -> None:
        runtime = build_runtime("mock")
        capabilities = runtime.describe_capabilities()
        self.assertEqual(capabilities.backend_id, "mock")
        self.assertEqual(capabilities.transport, "in-process")
        self.assertTrue(capabilities.supports_web_recon)
        self.assertFalse(capabilities.mcp_backed)

    def test_runtime_backend_metadata_lists_mock_and_mcp(self) -> None:
        metadata = list_runtime_backends()
        by_id = {item["backend_id"]: item for item in metadata}
        self.assertIn("mock", by_id)
        self.assertIn("mcp", by_id)
        self.assertEqual(by_id["mcp"]["transport"], "mcp-stdio")
        self.assertTrue(by_id["mcp"]["mcp_backed"])

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
            self.assertIn("workspace_rebuild_plan", output.artifacts)
            self.assertIn("rebuild_sign_rebuild", output.artifacts)
            self.assertIn("rebuild_replay_demo", output.artifacts)
            self.assertIn("rebuild_scrapy_middleware", output.artifacts)
            self.assertTrue(Path(output.artifacts["workspace_function_candidates"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_function_validations"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_function_validation_summary"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_rebuild_plan"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_sign_rebuild"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_replay_demo"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_scrapy_middleware"]).exists())
            self.assertIsNone(output.chrome_launch)
            self.assertIsNone(output.chrome_stop)


if __name__ == "__main__":
    unittest.main()
