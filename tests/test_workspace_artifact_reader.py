import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.tools.artifact_tools import make_read_workspace_artifact_tool


class WorkspaceArtifactReaderTests(unittest.TestCase):
    def test_reader_resolves_key_legacy_future_and_virtual_uri_to_canonical_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            payload = {"items": [1, 2, 3], "source": "legacy"}
            (workspace / "flow-timeline.json").write_text(json.dumps(payload), encoding="utf-8")
            tool = make_read_workspace_artifact_tool(root)

            refs = [
                "workspace_flow_timeline",
                "workspace/flow-timeline.json",
                "/workspace/timeline/flow-timeline.json",
                "virtual://workspace/timeline/flow-timeline.json",
            ]
            for artifact_ref in refs:
                with self.subTest(artifact_ref=artifact_ref):
                    result = tool(artifact_ref)
                    self.assertEqual(result["status"], "found")
                    self.assertEqual(result["content_type"], "json")
                    self.assertEqual(result["json"], payload)
                    self.assertEqual(result["resolution_status"], "resolved")
                    self.assertEqual(result["resolution"]["artifact_key"], "workspace_flow_timeline")
                    self.assertEqual(result["resolution"]["canonical_path"], "workspace/flow-timeline.json")
                    self.assertIn(str(workspace / "flow-timeline.json"), result["checked_paths"])
                    self.assertTrue(result["side_effect_policy"]["read_only"])
                    self.assertFalse(result["side_effect_policy"]["moves_artifacts"])
                    self.assertFalse(result["side_effect_policy"]["starts_browser"])

    def test_reader_uses_future_path_when_dual_write_artifact_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            future_dir = root / "workspace" / "timeline"
            future_dir.mkdir(parents=True)
            payload = {"items": ["future"], "source": "dual-write"}
            (future_dir / "flow-timeline.json").write_text(json.dumps(payload), encoding="utf-8")
            tool = make_read_workspace_artifact_tool(root)

            result = tool("virtual://workspace/timeline/flow-timeline.json")

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["json"], payload)
            self.assertEqual(result["path"], str(future_dir / "flow-timeline.json"))
            self.assertIn(str(root / "workspace" / "flow-timeline.json"), result["checked_paths"])
            self.assertIn(str(future_dir / "flow-timeline.json"), result["checked_paths"])

    def test_reader_supports_artifact_root_relative_fallback_for_unknown_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            (root / "custom").mkdir(parents=True)
            (root / "custom" / "note.txt").write_text("hello", encoding="utf-8")
            tool = make_read_workspace_artifact_tool(root)

            result = tool("custom/note.txt")

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["resolution_status"], "direct-path-fallback")
            self.assertEqual(result["content_type"], "text")
            self.assertEqual(result["content"], "hello")

    def test_reader_reports_missing_with_checked_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            tool = make_read_workspace_artifact_tool(root)

            result = tool("workspace_rebuild_plan")

            self.assertEqual(result["status"], "missing")
            self.assertEqual(result["resolution_status"], "resolved")
            self.assertEqual(result["resolution"]["artifact_key"], "workspace_rebuild_plan")
            self.assertIn(str(root / "workspace" / "rebuild-plan.json"), result["checked_paths"])
            self.assertIn(str(root / "workspace" / "rebuild" / "rebuild-plan.json"), result["checked_paths"])


if __name__ == "__main__":
    unittest.main()
