import unittest

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.schemas import ArtifactKind, ConfidenceLevel, ExecutionStatus, FinalResult, KeyFindings, ReverseMode, ReverseStage, TaskCard
from reverse_deepagent.tools.artifact_tools import make_export_reverse_artifacts_tool
from reverse_deepagent.tools.protection_tools import make_apply_minimal_protection_tool


class FakeBridge:
    def invoke(self, tool_name: str, params: dict):
        if tool_name == "inject_preload_script":
            return {"ok": True, "script": params["script"]}
        if tool_name == "export_session_report":
            return {"ok": True, "format": params.get("format")}
        raise AssertionError(f"unexpected tool {tool_name}")


class ProtectionAndArtifactToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = JSReverserRuntime(bridge=FakeBridge())

    def test_apply_minimal_protection_tool_returns_success_for_console_clear(self) -> None:
        tool = make_apply_minimal_protection_tool(self.runtime)
        payload = tool("console.clear", "{}")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["next_action"], "resume_recon")

    def test_export_reverse_artifacts_tool_returns_bundle(self) -> None:
        tool = make_export_reverse_artifacts_tool(self.runtime)
        final_result = FinalResult(
            task_card=TaskCard(
                target_url_or_file="https://example.com/search",
                target_param_or_api="x-sign",
                goal="找入口",
                boundaries="不登录",
            ),
            mode=ReverseMode.FULL_WORKFLOW,
            stage=ReverseStage.RECON,
            status=ExecutionStatus.PARTIAL,
            key_findings=KeyFindings(facts=["已捕获请求"]),
            next_action="move_to_source_analysis",
            confidence=ConfidenceLevel.MEDIUM,
        )
        payload = tool(final_result.model_dump_json())
        self.assertEqual(payload["exports"][0]["tool"], "export_session_report")
        self.assertEqual(payload["artifacts"][0]["kind"], ArtifactKind.EXPORT.value)


if __name__ == "__main__":
    unittest.main()
