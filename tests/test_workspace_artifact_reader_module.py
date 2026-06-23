import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.tools.artifact_tools import (
    audit_workspace_artifact_consumers_payload as compat_audit_workspace_artifact_consumers_payload,
    read_workspace_artifact_payload as compat_read_workspace_artifact_payload,
)
from reverse_deepagent.tools.workspace_artifact_reader import (
    audit_workspace_artifact_consumers_payload,
    read_workspace_artifact_payload,
)


class WorkspaceArtifactReaderModuleTests(unittest.TestCase):
    def test_reader_module_exports_low_level_payload_helpers_without_changing_compat_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "workspace").mkdir()
            (root / "workspace" / "task-card.json").write_text(
                json.dumps({"task": "demo"}),
                encoding="utf-8",
            )

            direct_read_payload = read_workspace_artifact_payload(
                artifact_ref="workspace_task_card",
                default_artifact_root=root,
            )
            compat_read_payload = compat_read_workspace_artifact_payload(
                artifact_ref="workspace_task_card",
                default_artifact_root=root,
            )
            direct_audit_payload = audit_workspace_artifact_consumers_payload()
            compat_audit_payload = compat_audit_workspace_artifact_consumers_payload()

        self.assertEqual(direct_read_payload["status"], "found")
        self.assertEqual(direct_read_payload["json"], {"task": "demo"})
        self.assertEqual(compat_read_payload["json"], direct_read_payload["json"])
        self.assertTrue(direct_read_payload["side_effect_policy"]["read_only"])
        self.assertEqual(direct_audit_payload["schema_version"], "reverse-deepagent.workspace-consumer-audit.v1")
        self.assertEqual(compat_audit_payload["schema_version"], direct_audit_payload["schema_version"])
        self.assertTrue(direct_audit_payload["side_effect_policy"]["read_only"])


if __name__ == "__main__":
    unittest.main()
