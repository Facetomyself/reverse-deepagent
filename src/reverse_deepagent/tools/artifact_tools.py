from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from reverse_deepagent.runtime.base import ReverseRuntime
from reverse_deepagent.schemas import FinalResult
from reverse_deepagent.workspace_contract import WorkspacePathResolution, WorkspacePathResolver


ArtifactTool = Callable[..., dict[str, Any]]


def make_export_reverse_artifacts_tool(runtime: ReverseRuntime) -> ArtifactTool:
    """Create a tool wrapper that exports runtime artifacts."""

    def export_reverse_artifacts(final_result_json: str | None = None) -> dict[str, Any]:
        final_result = FinalResult.model_validate_json(final_result_json) if final_result_json else None
        return runtime.export_reverse_artifacts(final_result=final_result).model_dump(mode="json")

    export_reverse_artifacts.__name__ = "export_reverse_artifacts"
    export_reverse_artifacts.__doc__ = "Export runtime artifacts and return a normalized export bundle."
    return export_reverse_artifacts


def make_read_workspace_artifact_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only resolver-backed workspace artifact reader tool."""

    root = Path(default_artifact_root)
    resolver = WorkspacePathResolver()

    def read_workspace_artifact(
        artifact_ref: str,
        artifact_root: str | None = None,
        max_chars: int = 20000,
    ) -> dict[str, Any]:
        """Read a workspace artifact by key, legacy path, future path, or virtual URI without mutating files."""

        effective_root = Path(artifact_root) if artifact_root else root
        resolution = resolver.resolve_artifact_key(artifact_ref) or resolver.resolve_path(artifact_ref)
        candidate_paths = _candidate_paths(effective_root, artifact_ref, resolution)
        checked_paths: list[str] = []
        for candidate in candidate_paths:
            checked_paths.append(str(candidate))
            if not candidate.exists() or not candidate.is_file():
                continue
            return _read_artifact_file(
                candidate,
                artifact_ref=artifact_ref,
                artifact_root=effective_root,
                resolution=resolution,
                checked_paths=checked_paths,
                max_chars=max_chars,
            )
        return {
            "status": "missing",
            "artifact_ref": artifact_ref,
            "artifact_root": str(effective_root),
            "resolution_status": "resolved" if resolution else "direct-path-fallback",
            "resolution": resolution.to_dict() if resolution else {},
            "checked_paths": checked_paths,
            "side_effect_policy": _reader_side_effect_policy(),
        }

    read_workspace_artifact.__name__ = "read_workspace_artifact"
    read_workspace_artifact.__doc__ = (
        "Read a workspace artifact by artifact key, legacy workspace/*.json path, "
        "future /workspace/<area>/ path, virtual://workspace/... URI, or artifact-root-relative path. "
        "The tool is read-only and does not migrate or dual-write artifacts."
    )
    return read_workspace_artifact


def _candidate_paths(root: Path, artifact_ref: str, resolution: WorkspacePathResolution | None) -> list[Path]:
    raw_candidates: list[str] = []
    if resolution is not None:
        raw_candidates.extend(resolution.read_paths)
        raw_candidates.extend((resolution.canonical_path, resolution.future_path, resolution.virtual_uri))
    else:
        raw_candidates.append(artifact_ref)
    paths: list[Path] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        path = _artifact_ref_to_filesystem_path(root, raw)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _artifact_ref_to_filesystem_path(root: Path, value: str) -> Path:
    value = str(value).strip()
    if value.startswith("virtual://"):
        parsed = urlparse(value)
        netloc = parsed.netloc.strip("/")
        path = parsed.path.strip("/")
        relative = "/".join(part for part in (netloc, path) if part)
        return root / relative
    if value.startswith("/workspace/"):
        return root / value.lstrip("/")
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _read_artifact_file(
    path: Path,
    *,
    artifact_ref: str,
    artifact_root: Path,
    resolution: WorkspacePathResolution | None,
    checked_paths: list[str],
    max_chars: int,
) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {
            "status": "error",
            "artifact_ref": artifact_ref,
            "artifact_root": str(artifact_root),
            "path": str(path),
            "error": f"artifact is not valid UTF-8 text: {exc}",
            "resolution_status": "resolved" if resolution else "direct-path-fallback",
            "resolution": resolution.to_dict() if resolution else {},
            "checked_paths": checked_paths,
            "side_effect_policy": _reader_side_effect_policy(),
        }
    parsed_json: Any | None = None
    parse_error = ""
    content_type = "text"
    if path.suffix.lower() == ".json" or raw_text.lstrip().startswith(("{", "[")):
        try:
            parsed_json = json.loads(raw_text)
            content_type = "json"
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
            content_type = "invalid-json"
    truncated = len(raw_text) > max_chars
    return {
        "status": "found",
        "artifact_ref": artifact_ref,
        "artifact_root": str(artifact_root),
        "path": str(path),
        "content_type": content_type,
        "content": raw_text[:max_chars],
        "content_truncated": truncated,
        "content_length": len(raw_text),
        "json": parsed_json if parsed_json is not None else None,
        "json_parse_error": parse_error,
        "resolution_status": "resolved" if resolution else "direct-path-fallback",
        "resolution": resolution.to_dict() if resolution else {},
        "checked_paths": checked_paths,
        "side_effect_policy": _reader_side_effect_policy(),
    }


def _reader_side_effect_policy() -> dict[str, bool]:
    return {
        "read_only": True,
        "writes_artifacts": False,
        "moves_artifacts": False,
        "creates_directories": False,
        "enables_dual_write": False,
        "changes_canonical_path": False,
        "starts_browser": False,
        "calls_mcp": False,
    }
