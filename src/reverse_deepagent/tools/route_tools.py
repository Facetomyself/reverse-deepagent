from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from reverse_deepagent.schemas import ConfidenceLevel, ReverseMode, ReverseStage, RouterResult, TaskCard

DEFAULT_JS_REVERSE_SKILL_ROOT = Path(os.environ.get("JS_REVERSE_SKILL_ROOT", str(Path.home() / ".codex/skills/js-reverse")))
_FIELD_KEYS = {
    "target_url_or_file": ["target_url_or_file", "target url or file", "目标页面", "目标文件"],
    "target_param_or_api": ["target_param_or_api", "target param or api", "目标参数", "参数", "api", "target_param"],
    "goal": ["goal", "目标", "任务目标"],
    "boundaries": ["boundaries", "边界", "限制"],
    "sample_request": ["sample_request", "sample request", "请求样本", "样本请求"],
    "protection_hints": ["protection_hints", "protection hints", "保护提示", "对抗提示"],
}
_URL_RE = re.compile(r"https?://[^\s]+")


def normalize_task_card(task_text: str) -> TaskCard:
    """Best-effort normalization from free-form task text into a TaskCard.

    The function first parses explicit key-value lines. When fields are missing,
    it falls back to lightweight heuristics so execution can continue without
    blocking on manual normalization.
    """

    parsed = _parse_key_value_lines(task_text)
    url = parsed.get("target_url_or_file") or _guess_target_url_or_file(task_text)
    target_param = parsed.get("target_param_or_api") or _guess_target_param_or_api(task_text)
    goal = parsed.get("goal") or task_text.strip()
    boundaries = parsed.get("boundaries") or "不登录，不做破坏性操作"
    sample_request = parsed.get("sample_request") or _guess_sample_request(task_text)
    protection_hints = _normalize_protection_hints(parsed.get("protection_hints"), task_text)

    return TaskCard(
        target_url_or_file=url,
        target_param_or_api=target_param,
        goal=goal,
        boundaries=boundaries,
        sample_request=sample_request,
        protection_hints=protection_hints,
    )


def route_reverse_task(task_text: str, skill_root: str | None = None) -> dict[str, Any]:
    """Route a reverse task using js-reverse manifests and lightweight policy heuristics."""

    task_card = normalize_task_card(task_text)
    result = route_from_task_card(task_card, task_text=task_text, skill_root=skill_root)
    return result.model_dump(mode="json")


def route_from_task_card(task_card: TaskCard, task_text: str | None = None, skill_root: str | None = None) -> RouterResult:
    manifests = load_route_manifests(skill_root)
    matched_intent = _match_intent(task_text or _task_card_to_text(task_card), manifests["intents"])

    if matched_intent:
        selected_mode = ReverseMode(matched_intent["route"]["mode"])
        selected_playbook = matched_intent["route"]["playbook"]
        reasoning = [f"命中 intent: {matched_intent['id']}"]
        confidence = ConfidenceLevel.HIGH
    else:
        selected_mode, selected_playbook, reasoning, confidence = _fallback_route(task_card, manifests)

    initial_stage = _lookup_start_stage(selected_mode, manifests["modes"])
    return RouterResult(
        selected_mode=selected_mode,
        selected_playbook=selected_playbook,
        initial_stage=initial_stage,
        reasoning=reasoning,
        confidence=confidence,
        next_action=_next_action_for_stage(initial_stage),
    )


def load_route_manifests(skill_root: str | None = None) -> dict[str, Any]:
    root = Path(skill_root) if skill_root else DEFAULT_JS_REVERSE_SKILL_ROOT
    manifest_dir = root / "manifests"
    return {
        "intents": _read_json(manifest_dir / "intents.json").get("intents", []),
        "default_route": _read_json(manifest_dir / "intents.json").get("default_route", {}),
        "modes": _read_json(manifest_dir / "modes.json").get("modes", []),
        "stages": _read_json(manifest_dir / "stages.json").get("stages", []),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_key_value_lines(task_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in task_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        for field, aliases in _FIELD_KEYS.items():
            for alias in aliases:
                normalized_alias = alias.rstrip("：:").lower()
                prefixes = [f"{normalized_alias}:", f"{normalized_alias}："]
                if any(lowered.startswith(prefix) for prefix in prefixes):
                    value = line.split("：", 1)[1] if "：" in line else line.split(":", 1)[1]
                    result[field] = value.strip()
                    break
            if field in result:
                break
    return result


def _guess_target_url_or_file(task_text: str) -> str:
    match = _URL_RE.search(task_text)
    if match:
        return match.group(0)
    return "about:blank"


def _guess_target_param_or_api(task_text: str) -> str:
    lowered = task_text.lower()
    for token in ("x-sign", "sign", "token", "cookie", "h5st", "a-bogus"):
        if token in lowered:
            return token
    return "unknown-target"


def _guess_sample_request(task_text: str) -> str | None:
    match = re.search(r"\b(GET|POST|PUT|DELETE|PATCH)\b\s+(/[^\s]+)", task_text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()} {match.group(2)}"
    return None


def _normalize_protection_hints(raw_value: str | None, task_text: str) -> list[str]:
    hints: list[str] = []
    if raw_value:
        hints.extend([item.strip() for item in re.split(r"[,，]", raw_value) if item.strip()])
    lowered = task_text.lower()
    auto_map = {
        "debugger": "debugger",
        "console.clear": "console.clear",
        "websocket": "websocket",
        "wasm": "wasm",
        "webpack": "webpack",
    }
    for needle, hint in auto_map.items():
        if needle in lowered and hint not in hints:
            hints.append(hint)
    return hints


def _task_card_to_text(task_card: TaskCard) -> str:
    return "\n".join(
        [
            task_card.target_url_or_file,
            task_card.target_param_or_api,
            task_card.goal,
            task_card.boundaries,
            task_card.sample_request or "",
            ", ".join(task_card.protection_hints),
        ]
    )


def _match_intent(task_text: str, intents: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = task_text.lower()
    for intent in intents:
        for keyword in intent.get("match_any", []):
            if keyword.lower() in lowered:
                return intent
    return None


def _fallback_route(task_card: TaskCard, manifests: dict[str, Any]) -> tuple[ReverseMode, str, list[str], ConfidenceLevel]:
    combined = _task_card_to_text(task_card).lower()

    if any(keyword in combined for keyword in ["打开页面", "点击", "selector", "截图", "dom"]):
        return ReverseMode.PAGE_AUTOMATION, "references/playbooks/page-automation.md", ["命中页面自动化特征"], ConfidenceLevel.MEDIUM
    if any(keyword in combined for keyword in ["webdriver", "ua", "user agent", "指纹", "风控", "验证码"]):
        return ReverseMode.STEALTH_CONTEXT, "references/playbooks/stealth-context.md", ["命中 stealth 特征"], ConfidenceLevel.MEDIUM
    if any(keyword in combined for keyword in ["h5st", "a-bogus", "falcon", "workflow", "blueprint"]):
        return ReverseMode.PARAMETER_WORKFLOW, "references/playbooks/parameter-workflow.md", ["命中参数 workflow 特征"], ConfidenceLevel.MEDIUM
    if any(keyword in combined for keyword in ["入口", "在哪生成", "谁生成的", "sign", "token"]):
        return ReverseMode.FIND_ENTRY, "references/playbooks/find-entry.md", ["命中入口定位特征"], ConfidenceLevel.MEDIUM
    if any(keyword in combined for keyword in ["解混淆", "deobfuscate", "控制流平坦化", "字符串表"]):
        return ReverseMode.AST_DEOBFUSCATE, "references/playbooks/ast-deobfuscate.md", ["命中解混淆特征"], ConfidenceLevel.MEDIUM
    if any(keyword in combined for keyword in ["hook fetch", "hook xhr", "运行时", "抓运行时参数"]):
        return ReverseMode.RUNTIME_OBSERVE, "references/playbooks/runtime-observe.md", ["命中运行时观测特征"], ConfidenceLevel.MEDIUM
    if any(keyword in combined for keyword in ["debugger", "console.clear", "尺寸检测", "反调试"]):
        return ReverseMode.DEBUG_BLOCKED, "references/playbooks/debug-blocked.md", ["命中调试阻塞特征"], ConfidenceLevel.MEDIUM

    default_route = manifests.get("default_route", {})
    return (
        ReverseMode(default_route.get("mode", ReverseMode.FULL_WORKFLOW.value)),
        default_route.get("playbook", "references/playbooks/full-workflow.md"),
        ["未命中显式 intent，使用 full-workflow 兜底"],
        ConfidenceLevel.LOW,
    )


def _lookup_start_stage(selected_mode: ReverseMode, modes: list[dict[str, Any]]) -> ReverseStage:
    for mode in modes:
        if mode.get("id") == selected_mode.value:
            return ReverseStage(mode.get("start_stage", ReverseStage.CONTEXT.value))
    return ReverseStage.CONTEXT


def _next_action_for_stage(stage: ReverseStage) -> str:
    return {
        ReverseStage.CONTEXT: "collect_context_then_delegate",
        ReverseStage.PAGE_ACTION: "delegate_to_web_recon",
        ReverseStage.NETWORK: "delegate_to_web_recon",
        ReverseStage.DETECTION_TRIAGE: "delegate_to_protector",
        ReverseStage.LOGIC_EXTRACT: "delegate_to_logic_extract",
        ReverseStage.RUNTIME_VERIFY: "delegate_to_web_recon",
    }.get(stage, "delegate_to_web_recon")
