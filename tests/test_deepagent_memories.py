import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.store.memory import InMemoryStore

from reverse_deepagent.agent import build_default_backend, build_memory_namespace, build_reverse_agent

REPO_ROOT = Path(__file__).resolve().parents[1]


class ToolFriendlyFakeMessagesListChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


def writer_model(path: str, content: str) -> ToolFriendlyFakeMessagesListChatModel:
    return ToolFriendlyFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "write_file", "args": {"file_path": path, "content": content}, "id": "call_write_memory"}],
            ),
            AIMessage(content="writer done"),
        ]
    )


def reader_model(path: str) -> ToolFriendlyFakeMessagesListChatModel:
    return ToolFriendlyFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "read_file", "args": {"file_path": path}, "id": "call_read_memory"}],
            ),
            AIMessage(content="reader done"),
        ]
    )


def first_tool_message_content(result: dict, name: str) -> str | None:
    for message in result.get("messages", []):
        if isinstance(message, ToolMessage) and message.name == name:
            return str(message.content)
    return None


class DeepAgentMemoriesTests(unittest.TestCase):
    def test_memory_namespace_normalization_and_validation(self) -> None:
        self.assertEqual(build_memory_namespace(None), ("reverse-deepagent", "default-user", "memories"))
        self.assertEqual(build_memory_namespace("user-a/project-b"), ("user-a", "project-b"))
        self.assertEqual(build_memory_namespace(["user-a", "project-b"]), ("user-a", "project-b"))
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            build_memory_namespace("")
        with self.assertRaisesRegex(ValueError, "wildcard"):
            build_memory_namespace(["user", "*"])
        with self.assertRaisesRegex(ValueError, "wildcard"):
            build_memory_namespace("user-*/project")

    def test_default_backend_routes_memories_to_store_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = build_default_backend(
                artifact_root=Path(tmpdir) / "artifacts",
                memory_store=InMemoryStore(),
                memory_namespace=("reverse-deepagent", "unit", "memories"),
            )
        self.assertIn("/memories/", backend.routes)
        self.assertIn("/artifacts/", backend.routes)

    def test_default_backend_can_disable_memories_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = build_default_backend(
                artifact_root=Path(tmpdir) / "artifacts",
                enable_memories=False,
            )
        self.assertNotIn("/memories/", backend.routes)
        self.assertIn("/artifacts/", backend.routes)

    def test_memories_persist_across_agent_instances_with_shared_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_store = InMemoryStore()
            namespace = ("reverse-deepagent", "unit", "memories")
            memory_path = "/memories/reverse-patterns.md"
            memory_content = "遇到 x-sign 时先搜 buildSign，再看 runtime context。"
            writer = build_reverse_agent(
                model=writer_model(memory_path, memory_content),
                artifact_root=Path(tmpdir) / "writer-artifacts",
                memory_store=memory_store,
                memory_namespace=namespace,
            )
            writer_result = writer.invoke({"messages": [{"role": "user", "content": "写入长期记忆"}]})
            self.assertIn("Updated file /memories/reverse-patterns.md", first_tool_message_content(writer_result, "write_file") or "")

            reader = build_reverse_agent(
                model=reader_model(memory_path),
                artifact_root=Path(tmpdir) / "reader-artifacts",
                memory_store=memory_store,
                memory_namespace=namespace,
            )
            reader_result = reader.invoke({"messages": [{"role": "user", "content": "读取长期记忆"}]})
            self.assertIn(memory_content, first_tool_message_content(reader_result, "read_file") or "")

    def test_memories_are_isolated_by_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_store = InMemoryStore()
            memory_path = "/memories/reverse-patterns.md"
            writer = build_reverse_agent(
                model=writer_model(memory_path, "namespace-a memory"),
                artifact_root=Path(tmpdir) / "writer-artifacts",
                memory_store=memory_store,
                memory_namespace=("reverse-deepagent", "namespace-a"),
            )
            writer.invoke({"messages": [{"role": "user", "content": "写入 A 命名空间"}]})
            reader = build_reverse_agent(
                model=reader_model(memory_path),
                artifact_root=Path(tmpdir) / "reader-artifacts",
                memory_store=memory_store,
                memory_namespace=("reverse-deepagent", "namespace-b"),
            )
            reader_result = reader.invoke({"messages": [{"role": "user", "content": "读取 B 命名空间"}]})
            self.assertNotIn("namespace-a memory", first_tool_message_content(reader_result, "read_file") or "")

    def test_deepagent_memory_smoke_script_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/run_deepagent_memory_smoke.py"),
                    "--artifact-root",
                    str(Path(tmpdir) / "artifacts"),
                ],
                check=True,
                text=True,
                capture_output=True,
                env=env,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["memory_content_found"])
            self.assertEqual(payload["writer_message_count"], 4)
            self.assertEqual(payload["reader_message_count"], 4)
            self.assertIn("ToolMessage", payload["writer_message_types"])
            self.assertIn("ToolMessage", payload["reader_message_types"])


if __name__ == "__main__":
    unittest.main()
