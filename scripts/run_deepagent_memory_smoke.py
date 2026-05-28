#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.store.memory import InMemoryStore

from reverse_deepagent.agent import build_memory_namespace, build_reverse_agent


class ToolFriendlyFakeMessagesListChatModel(FakeMessagesListChatModel):
    """Fake chat model that can be used with deepagents tool binding."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


def build_writer_model(memory_path: str, content: str) -> ToolFriendlyFakeMessagesListChatModel:
    return ToolFriendlyFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": memory_path, "content": content},
                        "id": "call_write_memory_1",
                    }
                ],
            ),
            AIMessage(content="memory write completed"),
        ]
    )


def build_reader_model(memory_path: str) -> ToolFriendlyFakeMessagesListChatModel:
    return ToolFriendlyFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": memory_path},
                        "id": "call_read_memory_1",
                    }
                ],
            ),
            AIMessage(content="memory read completed"),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a pure-python DeepAgents /memories/ smoke test.")
    parser.add_argument(
        "--artifact-root",
        default=str(Path(__file__).resolve().parents[1] / "artifacts/deepagents-memory-smoke"),
        help="Artifact output root directory.",
    )
    parser.add_argument("--memory-path", default="/memories/reverse-patterns.md", help="Virtual memory file path to write/read.")
    parser.add_argument(
        "--memory-content",
        default="sign 参数优先检查 buildSign / x-sign / token 相关源码命中。",
        help="Memory content written by the writer agent.",
    )
    parser.add_argument(
        "--memory-namespace",
        default="reverse-deepagent/smoke/memories",
        help="Slash-separated StoreBackend namespace.",
    )
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root)
    memory_store = InMemoryStore()
    namespace = build_memory_namespace(args.memory_namespace)

    writer = build_reverse_agent(
        model=build_writer_model(args.memory_path, args.memory_content),
        artifact_root=artifact_root / "writer",
        memory_store=memory_store,
        memory_namespace=namespace,
    )
    writer_result = writer.invoke({"messages": [{"role": "user", "content": "写入一条逆向长期记忆"}]})

    reader = build_reverse_agent(
        model=build_reader_model(args.memory_path),
        artifact_root=artifact_root / "reader",
        memory_store=memory_store,
        memory_namespace=namespace,
    )
    reader_result = reader.invoke({"messages": [{"role": "user", "content": "读取刚才写入的逆向长期记忆"}]})

    writer_tool_content = None
    reader_tool_content = None
    for message in writer_result.get("messages", []):
        if isinstance(message, ToolMessage) and message.name == "write_file":
            writer_tool_content = message.content
    for message in reader_result.get("messages", []):
        if isinstance(message, ToolMessage) and message.name == "read_file":
            reader_tool_content = message.content

    payload = {
        "artifact_root": str(artifact_root),
        "memory_path": args.memory_path,
        "memory_namespace": namespace,
        "writer_message_count": len(writer_result.get("messages", [])),
        "reader_message_count": len(reader_result.get("messages", [])),
        "writer_tool_content": writer_tool_content,
        "reader_tool_content": reader_tool_content,
        "memory_content_found": args.memory_content in str(reader_tool_content),
        "writer_message_types": [type(message).__name__ for message in writer_result.get("messages", [])],
        "reader_message_types": [type(message).__name__ for message in reader_result.get("messages", [])],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["memory_content_found"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
