from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED_VALUE = "<redacted>"

_SENSITIVE_KEYWORDS = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "cookie",
        "authorization",
        "proxyauthorization",
        "setcookie",
        "apikey",
        "credential",
        "csrf",
        "session",
        "bearer",
    }
)
_KEY_SPLIT_RE = re.compile(r"[^a-z0-9]+|(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_STRUCTURAL_MAPPING_KEYS = frozenset(
    {"headers", "responseheaders", "requestheaders", "localstorage", "sessionstorage"}
)
_AUTH_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9._~+/-]*)(?:\s+.+)?$")


def _key_parts(key: Any) -> set[str]:
    text = str(key or "")
    parts = {part.lower() for part in _KEY_SPLIT_RE.split(text) if part}
    compact = _NON_ALNUM_RE.sub("", text.lower())
    if compact:
        parts.add(compact)
    return parts


def is_sensitive_key(key: Any) -> bool:
    """Return True when a header/storage key name is likely to carry secret material."""

    parts = _key_parts(key)
    return any(
        part in _SENSITIVE_KEYWORDS or any(keyword in part for keyword in _SENSITIVE_KEYWORDS)
        for part in parts
    )


def redact_cookie_header(value: Any) -> str:
    """Redact cookie-like header values while preserving cookie / attribute names."""

    if value is None:
        return ""
    redacted_parts: list[str] = []
    for part in str(value).split(";"):
        stripped = part.strip()
        if not stripped:
            continue
        if "=" in stripped:
            name, _raw_value = stripped.split("=", 1)
            name = name.strip() or "<unnamed>"
            redacted_parts.append(f"{name}={REDACTED_VALUE}")
        else:
            redacted_parts.append(stripped)
    return "; ".join(redacted_parts)


def _redact_authorization_value(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return REDACTED_VALUE
    match = _AUTH_SCHEME_RE.match(stripped)
    if match and " " in stripped:
        return f"{match.group(1)} {REDACTED_VALUE}"
    return REDACTED_VALUE


def _redact_sensitive_scalar(key: Any, value: Any) -> Any:
    lowered = _NON_ALNUM_RE.sub("", str(key or "").lower())
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [_redact_sensitive_scalar(key, item) for item in value]
    if isinstance(value, str):
        if "cookie" in lowered:
            return redact_cookie_header(value)
        if "authorization" in lowered or value.lstrip().lower().startswith("bearer "):
            return _redact_authorization_value(value)
        return REDACTED_VALUE
    return REDACTED_VALUE


def redact_header_value(key: Any, value: Any) -> Any:
    """Redact one header-like value when its key is sensitive.

    Non-sensitive keys are returned unchanged. Sensitive authorization values keep
    only the auth scheme, and cookie-like values keep cookie / attribute names.
    """

    if not is_sensitive_key(key):
        return value
    return _redact_sensitive_scalar(key, value)


def redact_mapping(mapping: Mapping[Any, Any] | None) -> dict[Any, Any]:
    """Return a copy of a header/storage mapping with sensitive values redacted."""

    if not mapping:
        return {}
    redacted: dict[Any, Any] = {}
    for key, value in mapping.items():
        compact_key = _NON_ALNUM_RE.sub("", str(key or "").lower())
        if compact_key in _STRUCTURAL_MAPPING_KEYS and isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        elif is_sensitive_key(key):
            redacted[key] = redact_header_value(key, value)
        elif isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted


__all__ = [
    "REDACTED_VALUE",
    "is_sensitive_key",
    "redact_cookie_header",
    "redact_header_value",
    "redact_mapping",
]
