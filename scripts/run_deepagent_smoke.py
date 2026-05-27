#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage

from reverse_deepagent.agent import build_reverse_agent


class ToolFriendlyFakeMessagesListChatModel(FakeMessagesListChatModel):
    """Fake chat model that can be used with deepagents tool binding."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


def build_mock_model(task_text: str) -> ToolFriendlyFakeMessagesListChatModel:
    return ToolFriendlyFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "route_reverse_task",
                        "args": {"task_text": task_text},
                        "id": "call_route_1",
                    }
                ],
            ),
            AIMessage(content="deepagents invoke completed"),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a pure-python deepagents smoke test without external APIs.")
    parser.add_argument(
        "--task-text",
        default="http://localhost 找 sign 入口，并给出下一步建议",
        help="Free-form reverse task description.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(Path(__file__).resolve().parents[1] / "artifacts/deepagents-smoke"),
        help="Artifact output root directory.",
    )
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root)
    model = build_mock_model(args.task_text)
    agent = build_reverse_agent(model=model, artifact_root=artifact_root)
    result = agent.invoke({"messages": [{"role": "user", "content": args.task_text}]})

    route_result = None
    final_text = None
    messages = result.get("messages", [])
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == "route_reverse_task":
            try:
                route_result = json.loads(message.content)
            except Exception:
                route_result = {"text": message.content}
        if isinstance(message, AIMessage):
            final_text = message.content

    payload = {
        "task_text": args.task_text,
        "artifact_root": str(artifact_root),
        "message_count": len(messages),
        "route_result": route_result,
        "final_text": final_text,
        "message_types": [type(message).__name__ for message in messages],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
