from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

_RUNTIME_CONTEXT_METADATA_KEYS = {
    "sample_index",
    "collected_at_ms",
    "collectedAtMs",
    "environment_raw",
    "storage_raw",
}
_SENSITIVE_PATH_MARKERS = (
    "authorization",
    "auth",
    "cookie",
    "credential",
    "csrf",
    "jwt",
    "key",
    "password",
    "secret",
    "session",
    "token",
)
_SESSION_BOUND_PATH_MARKERS = (
    "authorization",
    "auth",
    "cookie",
    "csrf",
    "jwt",
    "session",
    "token",
)
_VOLATILE_PATH_MARKERS = (
    "nonce",
    "random",
    "salt",
    "timestamp",
    "time",
    "ts",
    "uuid",
)
_MISSING = object()


@dataclass(frozen=True, slots=True)
class RuntimeContextSample:
    """One collected runtime context sample for stability comparison."""

    sample_id: str
    context: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


def diff_runtime_context_samples(
    samples: Iterable[RuntimeContextSample | Mapping[str, Any]],
    *,
    requirements: Iterable[str] | None = None,
    captured_requirements: Iterable[str] | None = None,
    missing_requirements: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return a conservative, JSON-serializable stability diff for runtime context samples.

    The function is intentionally side-effect free and provider neutral. It does not collect
    runtime context itself; callers pass already captured browser/runtime samples.
    """

    normalized_samples = _normalize_samples(samples)
    requirement_list = _unique_strings(requirements or [])
    captured_list = _unique_strings(captured_requirements or [])
    missing_list = _unique_strings(missing_requirements or [item for item in requirement_list if item not in captured_list])
    if not normalized_samples:
        return {
            "status": "insufficient_samples",
            "stable": False,
            "sample_count": 0,
            "requirements": requirement_list,
            "captured_requirements": captured_list,
            "missing_requirements": missing_list,
            "stable_keys": [],
            "volatile_keys": [],
            "changes": {},
            "fields": [],
            "summary": _empty_summary(),
            "review_hints": ["runtime_context_missing_samples"],
            "notes": ["no runtime context samples were provided"],
        }

    flattened_samples = [_filter_runtime_context_flattened(_flatten_runtime_context(sample.context)) for sample in normalized_samples]
    all_paths = sorted({path for flat in flattened_samples for path in flat})
    field_records = [
        _build_field_record(path, flattened_samples, normalized_samples)
        for path in all_paths
    ]
    stable_keys = [record["path"] for record in field_records if record["classification"] in {"stable", "session_bound"}]
    volatile_keys = [
        record["path"]
        for record in field_records
        if record["classification"] in {"volatile", "missing_in_some_samples", "type_drift", "object_drift"}
    ]
    changes = {
        record["path"]: record["legacy_change_values"]
        for record in field_records
        if record.get("legacy_change_values")
    }
    for record in field_records:
        record.pop("legacy_change_values", None)

    summary = _summarize_fields(field_records, missing_list)
    review_hints = _review_hints(summary)
    status = "single_sample" if len(normalized_samples) == 1 else "analyzed"
    notes = [
        "multi-sample runtime context diff; volatile keys should be treated as runtime-bound inputs"
        if len(normalized_samples) >= 2
        else "single sample only; collect multiple samples to detect volatile context keys",
        "sample_index and collected_at_ms are metadata and excluded from stability decisions",
        "secret-like field previews are redacted to type, length, and digest metadata",
    ]
    return {
        "status": status,
        "legacy_status": "single_sample" if len(normalized_samples) == 1 else "multi_sample",
        "stable": not volatile_keys and not missing_list,
        "sample_count": len(normalized_samples),
        "requirements": requirement_list,
        "captured_requirements": captured_list,
        "missing_requirements": missing_list,
        "stable_keys": stable_keys,
        "volatile_keys": volatile_keys,
        "changes": changes,
        "fields": field_records,
        "summary": summary,
        "review_hints": review_hints,
        "notes": notes,
    }


def diff_runtime_context_payload(runtime_context: Mapping[str, Any]) -> dict[str, Any]:
    """Build a stability diff from the runtime-context artifact payload shape."""

    if not runtime_context:
        return {}
    requirements = [str(item) for item in runtime_context.get("detected_requirements", []) if item]
    captured = [str(item) for item in runtime_context.get("captured_requirements", []) if item]
    missing = [item for item in requirements if item not in captured]
    raw_samples = runtime_context.get("samples")
    samples = [item for item in raw_samples if isinstance(item, Mapping)] if isinstance(raw_samples, list) else []
    if not samples:
        samples = [runtime_context]
    return diff_runtime_context_samples(
        samples,
        requirements=requirements,
        captured_requirements=captured,
        missing_requirements=missing,
    )


def _normalize_samples(samples: Iterable[RuntimeContextSample | Mapping[str, Any]]) -> list[RuntimeContextSample]:
    normalized: list[RuntimeContextSample] = []
    for index, sample in enumerate(samples):
        if isinstance(sample, RuntimeContextSample):
            if isinstance(sample.context, Mapping):
                normalized.append(sample)
            continue
        if not isinstance(sample, Mapping):
            continue
        sample_id = str(sample.get("sample_id") or sample.get("sampleId") or sample.get("sample_index") or index)
        metadata = {
            key: sample[key]
            for key in ("sample_index", "collected_at_ms", "collectedAtMs")
            if key in sample
        }
        normalized.append(RuntimeContextSample(sample_id=sample_id, context=sample, metadata=metadata))
    return normalized


def _build_field_record(path: str, flattened_samples: list[dict[str, Any]], samples: list[RuntimeContextSample]) -> dict[str, Any]:
    values = [flat.get(path, _MISSING) for flat in flattened_samples]
    observed = [value for value in values if value is not _MISSING]
    missing_count = len(values) - len(observed)
    fingerprints = [_stable_json(value) for value in observed]
    unique_fingerprints = sorted(set(fingerprints))
    value_types = sorted({_json_type(value) for value in observed})
    sensitive = _is_sensitive_path(path)
    unique_values: list[Any] = []
    seen: set[str] = set()
    for value in observed:
        fingerprint = _stable_json(value)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique_values.append(value)
        if len(unique_values) >= 5:
            break
    if missing_count:
        unique_values.append(None)

    classification = _classify_field(path, values, observed, unique_fingerprints, value_types, missing_count)
    evidence = _field_evidence(path, classification, observed, missing_count, unique_fingerprints, value_types, sensitive)
    preview_values = unique_values[:5]
    return {
        "path": path,
        "classification": classification,
        "sample_count": len(values),
        "observed_count": len(observed),
        "missing_count": missing_count,
        "unique_value_count": len(unique_fingerprints),
        "value_types": value_types,
        "value_preview": [_preview_value(path, value) for value in preview_values],
        "evidence": evidence,
        "recommended_action": _recommended_action(classification),
        "sample_ids_observed": [sample.sample_id for sample, value in zip(samples, values, strict=False) if value is not _MISSING],
        "sample_ids_missing": [sample.sample_id for sample, value in zip(samples, values, strict=False) if value is _MISSING],
        "sensitive": sensitive,
        "legacy_change_values": _legacy_change_values(path, values, classification),
    }


def _classify_field(
    path: str,
    values: list[Any],
    observed: list[Any],
    unique_fingerprints: list[str],
    value_types: list[str],
    missing_count: int,
) -> str:
    if missing_count:
        return "missing_in_some_samples"
    if len(value_types) > 1:
        return "type_drift"
    if not observed:
        return "missing_in_some_samples"
    if len(unique_fingerprints) == 1:
        return "session_bound" if _is_session_bound_path(path) else "stable"
    if _contains_structural_values(observed):
        return "object_drift"
    return "volatile"


def _field_evidence(
    path: str,
    classification: str,
    observed: list[Any],
    missing_count: int,
    unique_fingerprints: list[str],
    value_types: list[str],
    sensitive: bool,
) -> list[str]:
    evidence = [
        f"classification={classification}",
        f"observed_count={len(observed)}",
        f"missing_count={missing_count}",
        f"unique_value_count={len(unique_fingerprints)}",
        f"value_types={','.join(value_types)}",
    ]
    if _is_volatile_path(path):
        evidence.append("path_marker=volatile_runtime_input")
    if _is_session_bound_path(path):
        evidence.append("path_marker=session_bound")
    if sensitive:
        evidence.append("secret_like_preview_redacted=true")
    if unique_fingerprints:
        evidence.append("value_digest_prefixes=" + ",".join(_digest_text(item)[:12] for item in unique_fingerprints[:5]))
    return evidence


def _recommended_action(classification: str) -> str:
    return {
        "stable": "safe_to_treat_as_constant_for_this_sample_set",
        "session_bound": "bind_from_runtime_session_or_fixture_context_do_not_hardcode",
        "volatile": "bind_dynamically_per_request_or_recompute_in_runtime",
        "missing_in_some_samples": "collect_more_samples_or_add_optional_runtime_binding_guard",
        "type_drift": "normalize_type_before_rebuild_or_keep_runtime_assisted",
        "object_drift": "compare_nested_shape_or_keep_object_runtime_bound",
    }.get(classification, "review_runtime_context_field")


def _legacy_change_values(path: str, values: list[Any], classification: str) -> list[Any]:
    if classification in {"stable", "session_bound"}:
        return []
    output: list[Any] = []
    seen: set[str] = set()
    sensitive = _is_sensitive_path(path)
    for value in values:
        item = None if value is _MISSING else value
        fingerprint = _stable_json(item)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        output.append(_preview_value(path, item) if sensitive else item)
        if len(output) >= 5:
            break
    return output


def _summarize_fields(fields: list[dict[str, Any]], missing_requirements: list[str]) -> dict[str, Any]:
    classifications = [str(field.get("classification")) for field in fields]
    return {
        "field_count": len(fields),
        "stable_field_count": classifications.count("stable"),
        "volatile_field_count": classifications.count("volatile"),
        "session_bound_field_count": classifications.count("session_bound"),
        "missing_field_count": classifications.count("missing_in_some_samples"),
        "type_drift_field_count": classifications.count("type_drift"),
        "object_drift_field_count": classifications.count("object_drift"),
        "missing_requirement_count": len(missing_requirements),
        "secret_like_field_count": sum(1 for field in fields if field.get("sensitive")),
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "field_count": 0,
        "stable_field_count": 0,
        "volatile_field_count": 0,
        "session_bound_field_count": 0,
        "missing_field_count": 0,
        "type_drift_field_count": 0,
        "object_drift_field_count": 0,
        "missing_requirement_count": 0,
        "secret_like_field_count": 0,
    }


def _review_hints(summary: Mapping[str, Any]) -> list[str]:
    hints: list[str] = []
    if summary.get("stable_field_count"):
        hints.append("runtime_context_stable_fields_detected")
    if summary.get("session_bound_field_count"):
        hints.append("runtime_context_session_bound_fields_detected")
    if summary.get("volatile_field_count"):
        hints.append("runtime_context_volatile_fields_detected")
    if summary.get("missing_field_count") or summary.get("missing_requirement_count"):
        hints.append("runtime_context_missing_fields_detected")
    if summary.get("type_drift_field_count"):
        hints.append("runtime_context_type_drift_detected")
    if summary.get("object_drift_field_count"):
        hints.append("runtime_context_object_drift_detected")
    if summary.get("secret_like_field_count"):
        hints.append("runtime_context_secret_like_values_redacted")
    return hints


def _preview_value(path: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "missing", "value": None}
    value_type = _json_type(value)
    stable = _stable_json(value)
    digest = _digest_text(stable)
    if _is_sensitive_path(path):
        return {
            "redacted": True,
            "type": value_type,
            "length": _value_length(value),
            "digest": digest[:16],
        }
    if isinstance(value, (dict, list)):
        return {
            "redacted": False,
            "type": value_type,
            "length": _value_length(value),
            "shape": _shape(value),
            "digest": digest[:16],
        }
    if isinstance(value, str):
        return {
            "redacted": False,
            "type": value_type,
            "length": len(value),
            "value": value if len(value) <= 80 else value[:77] + "...",
            "digest": digest[:16],
        }
    return {"redacted": False, "type": value_type, "value": value, "digest": digest[:16]}


def _value_length(value: Any) -> int | None:
    if isinstance(value, (str, list, tuple, dict)):
        return len(value)
    return None


def _shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_type(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))[:20]}
    if isinstance(value, list):
        return {"length": len(value), "item_types": sorted({_json_type(item) for item in value})}
    return _json_type(value)


def _contains_structural_values(values: Iterable[Any]) -> bool:
    return any(isinstance(value, (dict, list)) for value in values)


def _is_sensitive_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in _SENSITIVE_PATH_MARKERS)


def _is_session_bound_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in _SESSION_BOUND_PATH_MARKERS)


def _is_volatile_path(path: str) -> bool:
    lowered = path.lower()
    parts = [part for part in re.split(r"[^a-z0-9]+", lowered) if part]
    return any(marker in parts or marker in lowered for marker in _VOLATILE_PATH_MARKERS)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float" if math.isfinite(value) else "nonfinite_float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _stable_json(value: Any) -> str:
    if value is _MISSING:
        return "__MISSING__"
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unique_strings(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _filter_runtime_context_flattened(flat: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in flat.items()
        if key
        and key.split(".")[-1] not in _RUNTIME_CONTEXT_METADATA_KEYS
        and not key.endswith("_raw")
        and not key.startswith("environment_raw")
        and not key.startswith("storage_raw")
        and not key.startswith("samples.")
        and ".environment_raw" not in key
        and ".storage_raw" not in key
    }


def _flatten_runtime_context(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            output.update(_flatten_runtime_context(item, next_prefix))
        return output
    if isinstance(value, list):
        return {prefix: value}
    return {prefix: value}
