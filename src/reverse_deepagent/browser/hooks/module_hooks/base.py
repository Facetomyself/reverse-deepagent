"""module_hooks.base — split from monolithic module_hooks.py (B1 consolidation)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.collectors.scripts import ScriptCollector


JS_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")

JS_DOTTED_PATH_RE = re.compile(r"^(?:window\.)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$")

def _module_call_path(require_path: str, module_id: str) -> str:
    module_literal = module_id if re.fullmatch(r"\d+", module_id) else json.dumps(module_id, ensure_ascii=False)
    return f"{require_path}({module_literal})"

def _export_access_path(base_path: str, export_name: str) -> str:
    if JS_IDENTIFIER_RE.fullmatch(export_name):
        return f"{base_path}.{export_name}"
    return f"{base_path}[{json.dumps(export_name, ensure_ascii=False)}]"

def _module_export_hook_path(require_path: str, module_id: str, export_name: str) -> str:
    return _export_access_path(_module_call_path(require_path, module_id), export_name)

def _first_dict(context: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = context.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}

def _list_dicts(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []

def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if item is not None] if isinstance(value, list) else []

def _clip(value: Any, max_length: int) -> str:
    return str(value or "").strip()[: max(1, max_length)]
