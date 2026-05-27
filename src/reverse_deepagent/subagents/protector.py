from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.runtime.base import ReverseRuntime
from reverse_deepagent.schemas import ProtectionResult
from reverse_deepagent.tools.protection_tools import make_apply_minimal_protection_tool

PROTECTOR_SUBAGENT_NAME = "protector"
PROTECTOR_SUBAGENT_DESCRIPTION = "处理 debugger、console.clear、尺寸检测、redirect 等最小 protection 修补任务。"


def load_protector_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parents[1] / "prompts" / "protector.txt"
    return path.read_text(encoding="utf-8")


def build_protector_subagent(runtime: ReverseRuntime, prompt_path: str | Path | None = None) -> dict[str, Any]:
    return {
        "name": PROTECTOR_SUBAGENT_NAME,
        "description": PROTECTOR_SUBAGENT_DESCRIPTION,
        "system_prompt": load_protector_prompt(prompt_path),
        "tools": [make_apply_minimal_protection_tool(runtime)],
        "response_format": ProtectionResult,
    }
