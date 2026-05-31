from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from reverse_deepagent.subagents.browser_runtime import build_browser_runtime_subagent
from reverse_deepagent.subagents.debugger import build_debugger_subagent
from reverse_deepagent.subagents.delivery import build_delivery_subagent
from reverse_deepagent.subagents.hook import build_hook_subagent
from reverse_deepagent.subagents.protector import build_protector_subagent
from reverse_deepagent.subagents.rebuild import build_rebuild_subagent
from reverse_deepagent.subagents.review import build_review_subagent
from reverse_deepagent.subagents.router import build_router_subagent
from reverse_deepagent.subagents.timeline import build_timeline_subagent
from reverse_deepagent.subagents.web_recon import build_web_recon_subagent
from reverse_deepagent.tools.artifact_tools import make_read_workspace_artifact_tool
from reverse_deepagent.tools.rebuild_tools import make_build_rebuild_delivery_tool
from reverse_deepagent.tools.route_tools import DEFAULT_JS_REVERSE_SKILL_ROOT, route_reverse_task

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = DEFAULT_REPO_ROOT / "artifacts"
DEFAULT_MEMORY_NAMESPACE = ("reverse-deepagent", "default-user", "memories")
_DEFAULT_MEMORY_STORE: InMemoryStore | None = None


def get_default_memory_store() -> InMemoryStore:
    """Return the process-local default memory store for /memories/ smoke runs."""

    global _DEFAULT_MEMORY_STORE
    if _DEFAULT_MEMORY_STORE is None:
        _DEFAULT_MEMORY_STORE = InMemoryStore()
    return _DEFAULT_MEMORY_STORE


def build_memory_namespace(namespace: Sequence[str] | str | None = None) -> tuple[str, ...]:
    """Normalize a memory namespace into a StoreBackend-compatible tuple."""

    if namespace is None:
        return DEFAULT_MEMORY_NAMESPACE
    if isinstance(namespace, str):
        parts = tuple(part for part in namespace.split("/") if part)
    else:
        parts = tuple(str(part) for part in namespace if str(part))
    if not parts:
        raise ValueError("memory namespace must not be empty")
    if any("*" in part for part in parts):
        raise ValueError("memory namespace must not contain wildcard '*'")
    return parts


def load_coordinator_prompt(prompt_path: str | Path | None = None) -> str:
    path = Path(prompt_path) if prompt_path else Path(__file__).resolve().parent / "prompts" / "coordinator.txt"
    return path.read_text(encoding="utf-8")


def build_default_backend(
    artifact_root: str | Path | None = None,
    *,
    enable_memories: bool = True,
    memory_store: BaseStore | None = None,
    memory_namespace: Sequence[str] | str | None = None,
) -> CompositeBackend:
    root = Path(artifact_root) if artifact_root else DEFAULT_ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    routes: dict[str, Any] = {
        "/artifacts/": FilesystemBackend(root_dir=str(root), virtual_mode=True),
    }
    if enable_memories:
        namespace = build_memory_namespace(memory_namespace)
        store = memory_store or get_default_memory_store()
        routes["/memories/"] = StoreBackend(
            store=store,
            namespace=lambda _runtime, namespace=namespace: namespace,
        )
    return CompositeBackend(
        default=StateBackend(),
        routes=routes,
    )


def build_reverse_agent(
    model: Any,
    *,
    runtime: Any | None = None,
    artifact_root: str | Path | None = None,
    skill_root: str | None = None,
    extra_tools: Sequence[Any] | None = None,
    extra_subagents: Sequence[Any] | None = None,
    enable_memories: bool = True,
    memory_store: BaseStore | None = None,
    memory_namespace: Sequence[str] | str | None = None,
    debug: bool = False,
):
    """Build the minimal reverse deep agent scaffold.

    The scaffold wires coordinator + router by default, and can attach runtime-backed
    subagents such as web_recon and protector when a runtime implementation is provided.
    """

    effective_skill_root = skill_root or str(DEFAULT_JS_REVERSE_SKILL_ROOT)
    effective_artifact_root = Path(artifact_root) if artifact_root else DEFAULT_ARTIFACT_ROOT

    def route_reverse_task_tool(task_text: str) -> dict[str, Any]:
        """Route a reverse task using js-reverse manifests and route policy."""
        return route_reverse_task(task_text=task_text, skill_root=effective_skill_root)

    route_reverse_task_tool.__name__ = "route_reverse_task"
    tools = [
        route_reverse_task_tool,
        make_read_workspace_artifact_tool(effective_artifact_root),
        make_build_rebuild_delivery_tool(effective_artifact_root),
        *(extra_tools or []),
    ]
    subagents = [
        build_router_subagent(skill_root=effective_skill_root),
        build_debugger_subagent(artifact_root=effective_artifact_root),
        build_hook_subagent(artifact_root=effective_artifact_root),
        build_timeline_subagent(artifact_root=effective_artifact_root),
        build_review_subagent(artifact_root=effective_artifact_root),
        build_rebuild_subagent(artifact_root=effective_artifact_root),
        build_delivery_subagent(artifact_root=effective_artifact_root),
    ]
    if runtime is not None:
        subagents.extend([
            build_browser_runtime_subagent(runtime),
            build_web_recon_subagent(runtime),
            build_protector_subagent(runtime),
        ])
    subagents.extend(extra_subagents or [])

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=load_coordinator_prompt(),
        subagents=subagents,
        backend=build_default_backend(
            effective_artifact_root,
            enable_memories=enable_memories,
            memory_store=memory_store,
            memory_namespace=memory_namespace,
        ),
        debug=debug,
        name="reverse-deepagent-demo",
    )
