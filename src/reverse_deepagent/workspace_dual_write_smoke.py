from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from reverse_deepagent.coordinator import run_reverse_pipeline
from reverse_deepagent.tools.workspace_dual_write_pilot import review_workspace_dual_write_pilot_workflow_payload

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = DEFAULT_REPO_ROOT / "artifacts" / "workspace-dual-write-pilot-smoke"
DEFAULT_TASK_TEXT = "https://example.com/search 找 sign 入口，并给出下一步建议"
DEFAULT_ARTIFACT_KEYS = ("workspace_task_card",)


def _parse_artifact_keys(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_ARTIFACT_KEYS)
    keys = [item.strip() for item in value.split(",") if item.strip()]
    return list(dict.fromkeys(keys)) or list(DEFAULT_ARTIFACT_KEYS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a pure-python reviewed scoped workspace dual-write pilot smoke. "
            "This uses the mock Web runtime, writes only the requested scoped future paths, "
            "and verifies the observed workspace-dual-write-plan through the review workflow."
        )
    )
    parser.add_argument("--task-text", default=DEFAULT_TASK_TEXT, help="Free-form Web reverse task used by the mock pipeline.")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT), help="Artifact output root directory.")
    parser.add_argument(
        "--artifact-keys",
        default=",".join(DEFAULT_ARTIFACT_KEYS),
        help="Comma-separated reviewed low-risk workspace artifact keys to dual-write in this pilot.",
    )
    parser.add_argument(
        "--no-write-result",
        action="store_true",
        help="Do not write workspace/workspace-dual-write-pilot-result.json; keep workflow verification read-only.",
    )
    return parser


def run_workspace_dual_write_pilot_smoke(
    *,
    task_text: str = DEFAULT_TASK_TEXT,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    artifact_keys: Sequence[str] = DEFAULT_ARTIFACT_KEYS,
    write_result: bool = True,
) -> dict[str, object]:
    root = Path(artifact_root)
    scoped_keys = list(dict.fromkeys(str(item).strip() for item in artifact_keys if str(item).strip())) or list(DEFAULT_ARTIFACT_KEYS)
    pipeline = run_reverse_pipeline(
        task_text=task_text,
        artifact_root=root,
        runtime_kind="mock",
        enable_workspace_dual_write=True,
        workspace_dual_write_artifact_keys=scoped_keys,
    )
    workflow = review_workspace_dual_write_pilot_workflow_payload(
        default_artifact_root=root,
        artifact_keys_json=json.dumps(scoped_keys, ensure_ascii=False),
        workspace_dual_write_plan_artifact_ref="workspace_dual_write_plan",
        write_result=write_result,
    )
    result_artifact = workflow.get("pilot_result", {}).get("result_artifact", {}) if isinstance(workflow.get("pilot_result"), dict) else {}
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-smoke.v1",
        "ok": workflow.get("status") == "verified",
        "task_text": task_text,
        "artifact_root": str(root),
        "runtime": "mock",
        "selected_artifact_keys": scoped_keys,
        "pipeline": {
            "final_status": pipeline.final_result.status,
            "artifact_count": len(pipeline.artifacts),
            "workspace_dual_write_plan": pipeline.artifacts.get("workspace_dual_write_plan"),
            "backend_artifact_manifest": pipeline.artifacts.get("workspace_backend_artifact_manifest"),
        },
        "workflow": workflow,
        "result_artifact": result_artifact,
        "side_effect_boundary": {
            "starts_browser": False,
            "calls_mcp": False,
            "runtime_kind": "mock",
            "enables_workspace_dual_write": True,
            "scoped_artifact_keys_only": scoped_keys,
            "changes_canonical_paths": False,
            "migrates_paths": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = run_workspace_dual_write_pilot_smoke(
        task_text=args.task_text,
        artifact_root=args.artifact_root,
        artifact_keys=_parse_artifact_keys(args.artifact_keys),
        write_result=not args.no_write_result,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
