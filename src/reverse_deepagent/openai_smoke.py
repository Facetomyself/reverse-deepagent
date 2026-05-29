from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

from langchain_core.messages import AIMessage, ToolMessage

from reverse_deepagent.agent import build_reverse_agent

DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts/openai-smoke"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a real OpenAI-backed DeepAgents smoke test.")
    parser.add_argument(
        "--task-text",
        default="http://localhost 找 sign 入口，并给出下一步建议。先调用 route_reverse_task 工具完成路由。",
        help="Free-form reverse task description passed to the agent.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(DEFAULT_ARTIFACT_ROOT),
        help="Artifact output root directory.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        help="OpenAI model name. Defaults to OPENAI_MODEL or gpt-5.5.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("OPENAI_TIMEOUT", "120")),
        help="OpenAI request timeout in seconds.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.environ.get("OPENAI_MAX_RETRIES", "2")),
        help="OpenAI SDK max retry count.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Optional temperature. Omit by default because some reasoning models do not support arbitrary temperature.",
    )
    return parser


def build_openai_model(args: argparse.Namespace) -> Any:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set. Export it first, for example: "
            'export OPENAI_API_KEY="sk-..."'
        )
    try:
        from langchain_openai import ChatOpenAI
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "langchain-openai is not installed. Install the optional dependency with: "
            'uv pip install --python "<repo-root>/.venv/bin/python" -e ".[llm]"'
        ) from exc

    kwargs: dict[str, Any] = {
        "model": args.model,
        "timeout": args.timeout,
        "max_retries": args.max_retries,
    }
    if args.temperature is not None:
        kwargs["temperature"] = args.temperature
    return ChatOpenAI(**kwargs)


def summarize_messages(messages: list[Any]) -> dict[str, Any]:
    route_result = None
    final_text = None
    tool_messages: list[dict[str, Any]] = []
    ai_messages = 0
    for message in messages:
        if isinstance(message, ToolMessage):
            tool_messages.append({"name": message.name, "content_preview": str(message.content)[:500]})
            if message.name == "route_reverse_task":
                try:
                    route_result = json.loads(message.content)
                except Exception:
                    route_result = {"text": message.content}
        elif isinstance(message, AIMessage):
            ai_messages += 1
            if message.content:
                final_text = message.content
    return {
        "message_count": len(messages),
        "ai_message_count": ai_messages,
        "tool_messages": tool_messages,
        "route_result": route_result,
        "final_text": final_text,
        "message_types": [type(message).__name__ for message in messages],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifact_root = Path(args.artifact_root)
    model = build_openai_model(args)
    agent = build_reverse_agent(model=model, artifact_root=artifact_root)
    result = agent.invoke({"messages": [{"role": "user", "content": args.task_text}]})
    messages = result.get("messages", [])
    payload = {
        "ok": True,
        "provider": "openai",
        "model": args.model,
        "task_text": args.task_text,
        "artifact_root": str(artifact_root),
        **summarize_messages(messages),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
