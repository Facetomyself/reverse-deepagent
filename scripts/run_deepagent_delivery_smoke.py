#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage

from reverse_deepagent.agent import build_reverse_agent
from reverse_deepagent.coordinator import run_reverse_pipeline


class ToolFriendlyFakeMessagesListChatModel(FakeMessagesListChatModel):
    """Fake chat model that can be used with deepagents tool binding."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


def build_mock_model(task_card_json: str, final_result_json: str, artifact_root: str) -> ToolFriendlyFakeMessagesListChatModel:
    return ToolFriendlyFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "build_rebuild_delivery",
                        "args": {
                            "task_card_json": task_card_json,
                            "final_result_json": final_result_json,
                            "artifact_root": artifact_root,
                        },
                        "id": "call_rebuild_delivery_1",
                    }
                ],
            ),
            AIMessage(content="rebuild delivery completed"),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a pure-python deepagents rebuild delivery smoke test.")
    parser.add_argument(
        "--task-text",
        default="https://example.com/search 找 sign 入口，并生成纯算 replay 交付包",
        help="Free-form reverse task description.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(Path(__file__).resolve().parents[1] / "artifacts/deepagents-delivery-smoke"),
        help="Artifact output root directory.",
    )
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root)
    seed_output = run_reverse_pipeline(
        task_text=args.task_text,
        artifact_root=artifact_root / "seed",
        runtime_kind="mock",
    )
    task_card_json = seed_output.final_result.task_card.model_dump_json()
    final_result_json = seed_output.final_result.model_dump_json()

    model = build_mock_model(
        task_card_json=task_card_json,
        final_result_json=final_result_json,
        artifact_root=str(artifact_root / "delivery"),
    )
    agent = build_reverse_agent(model=model, artifact_root=artifact_root / "agent")
    result = agent.invoke({"messages": [{"role": "user", "content": args.task_text}]})

    delivery_result = None
    final_text = None
    messages = result.get("messages", [])
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == "build_rebuild_delivery":
            try:
                delivery_result = json.loads(message.content)
            except Exception:
                delivery_result = {"text": message.content}
        if isinstance(message, AIMessage):
            final_text = message.content

    payload = {
        "task_text": args.task_text,
        "artifact_root": str(artifact_root),
        "message_count": len(messages),
        "delivery_result": delivery_result,
        "final_text": final_text,
        "message_types": [type(message).__name__ for message in messages],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
