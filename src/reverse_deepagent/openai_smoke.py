from __future__ import annotations

import argparse
import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from langchain_core.messages import AIMessage, ToolMessage

from reverse_deepagent.agent import build_reverse_agent

DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = DEFAULT_REPO_ROOT / "config.toml"
DEFAULT_ARTIFACT_ROOT = DEFAULT_REPO_ROOT / "artifacts/openai-smoke"


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str | None
    model: str
    timeout: float
    max_retries: int
    temperature: float | None = None
    base_url: str | None = None
    organization: str | None = None
    config_path: Path | None = None


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
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Optional TOML config path. Defaults to <repo-root>/config.toml when it exists.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI model name. Precedence: CLI, OPENAI_MODEL, config.toml, gpt-5.5.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="OpenAI request timeout in seconds. Precedence: CLI, OPENAI_TIMEOUT, config.toml, 120.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="OpenAI SDK max retry count. Precedence: CLI, OPENAI_MAX_RETRIES, config.toml, 2.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Optional temperature. Omit by default because some reasoning models do not support arbitrary temperature.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional OpenAI-compatible base URL. Precedence: CLI, OPENAI_BASE_URL, config.toml.",
    )
    parser.add_argument(
        "--organization",
        default=None,
        help="Optional OpenAI organization id. Precedence: CLI, OPENAI_ORG_ID/OPENAI_ORGANIZATION, config.toml.",
    )
    return parser


def load_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    config_path = Path(path).expanduser()
    if not config_path.exists():
        return {}
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a TOML table: {config_path}")
    return data


def read_section(config: Mapping[str, Any], *names: str) -> Mapping[str, Any]:
    for name in names:
        current: Any = config
        for part in name.split("."):
            if not isinstance(current, Mapping):
                current = None
                break
            current = current.get(part)
        if isinstance(current, Mapping):
            return current
    return {}


def first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def optional_float(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number, got {value!r}") from exc


def optional_int(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer, got {value!r}") from exc


def resolve_openai_settings(args: argparse.Namespace, environ: Mapping[str, str] | None = None) -> OpenAISettings:
    env = os.environ if environ is None else environ
    config_path = Path(args.config).expanduser() if args.config else None
    config = load_config(config_path)
    section = read_section(config, "openai", "llm.openai")

    api_key = first_value(
        env.get("OPENAI_API_KEY"),
        section.get("api_key"),
    )
    model = first_value(
        args.model,
        env.get("OPENAI_MODEL"),
        section.get("model"),
        DEFAULT_OPENAI_MODEL,
    )
    timeout = optional_float(
        first_value(args.timeout, env.get("OPENAI_TIMEOUT"), section.get("timeout"), 120),
        "OpenAI timeout",
    )
    max_retries = optional_int(
        first_value(args.max_retries, env.get("OPENAI_MAX_RETRIES"), section.get("max_retries"), 2),
        "OpenAI max_retries",
    )
    temperature = optional_float(
        first_value(args.temperature, env.get("OPENAI_TEMPERATURE"), section.get("temperature")),
        "OpenAI temperature",
    )
    base_url = first_value(
        args.base_url,
        env.get("OPENAI_BASE_URL"),
        section.get("base_url"),
    )
    organization = first_value(
        args.organization,
        env.get("OPENAI_ORG_ID"),
        env.get("OPENAI_ORGANIZATION"),
        section.get("organization"),
        section.get("org_id"),
    )

    return OpenAISettings(
        api_key=str(api_key) if api_key else None,
        model=str(model),
        timeout=timeout if timeout is not None else 120.0,
        max_retries=max_retries if max_retries is not None else 2,
        temperature=temperature,
        base_url=str(base_url) if base_url else None,
        organization=str(organization) if organization else None,
        config_path=config_path if config_path and config_path.exists() else None,
    )


def build_openai_model(settings: OpenAISettings) -> Any:
    if not settings.api_key:
        config_hint = f' or add [openai].api_key to "{DEFAULT_CONFIG_PATH}"'
        raise SystemExit(
            "OpenAI API key is not set. Export it first, for example: "
            'export OPENAI_API_KEY="sk-..."'
            f"{config_hint}."
        )
    try:
        from langchain_openai import ChatOpenAI
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "langchain-openai is not installed. Install the optional dependency with: "
            'uv pip install --python "<repo-root>/.venv/bin/python" -e ".[llm]"'
        ) from exc

    kwargs: dict[str, Any] = {
        "api_key": settings.api_key,
        "model": settings.model,
        "timeout": settings.timeout,
        "max_retries": settings.max_retries,
    }
    if settings.temperature is not None:
        kwargs["temperature"] = settings.temperature
    if settings.base_url is not None:
        kwargs["base_url"] = settings.base_url
    if settings.organization is not None:
        kwargs["organization"] = settings.organization
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
    settings = resolve_openai_settings(args)
    artifact_root = Path(args.artifact_root)
    model = build_openai_model(settings)
    agent = build_reverse_agent(model=model, artifact_root=artifact_root)
    result = agent.invoke({"messages": [{"role": "user", "content": args.task_text}]})
    messages = result.get("messages", [])
    payload = {
        "ok": True,
        "provider": "openai",
        "model": settings.model,
        "config_path": str(settings.config_path) if settings.config_path else None,
        "task_text": args.task_text,
        "artifact_root": str(artifact_root),
        **summarize_messages(messages),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
