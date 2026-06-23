"""Split the monolithic module_hooks.py into a domain-organized package.

Strategy: pure physical relocation. Public class/function names and the
`from .module_hooks import (...)` contract stay identical. The original file
becomes a package whose __init__.py re-exports every symbol.

Domains (by symbol-name prefix):
  base          -> module-level helpers + regexes (shared foundation)
  module_io     -> ModuleHook* / ModuleDiscovery*  (lowest layer)
  async_chunk   -> AsyncChunk*
  federation    -> ModuleFederation* + RecursiveContinuationReadiness*
  custom_loader -> CustomLoader*  (depends on async_chunk + module_io)

Run with --dry-run first to inspect classification, then --write.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

HOOKS = Path("src/reverse_deepagent/browser/hooks")
BACKUP = HOOKS / "module_hooks_pkg" / "_original_backup.py"

# Symbols that live in base.py (module-level helpers / regexes).
BASE_NAMES = {
    "JS_IDENTIFIER_RE",
    "JS_DOTTED_PATH_RE",
    "_module_call_path",
    "_export_access_path",
    "_module_export_hook_path",
    "_first_dict",
    "_list_dicts",
    "_string_list",
    "_clip",
}


def classify(name: str) -> str:
    if name in BASE_NAMES:
        return "base"
    if name.startswith(("ModuleHook", "ModuleDiscovery")):
        return "module_io"
    if name.startswith("AsyncChunk"):
        return "async_chunk"
    if name.startswith("ModuleFederation") or name.startswith("RecursiveContinuationReadiness"):
        return "federation"
    if name.startswith("CustomLoader"):
        return "custom_loader"
    return "UNCLASSIFIED"


def node_name(node: ast.stmt) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign):
        tgt = node.targets[0]
        if isinstance(tgt, ast.Name):
            return tgt.id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="actually write files")
    args = ap.parse_args()

    raw = BACKUP.read_text(encoding="utf-8")
    tree = ast.parse(raw)
    lines = raw.splitlines(keepends=True)

    # Collect leading import block (everything before first class/func/assign symbol).
    import_lines: list[str] = []
    domains: dict[str, list[str]] = {
        "base": [],
        "module_io": [],
        "async_chunk": [],
        "federation": [],
        "custom_loader": [],
    }
    unclassified: list[tuple[str, str]] = []

    # decorators precede the def line; use the decorator's first line if present.
    def seg_start(node: ast.stmt) -> int:
        if getattr(node, "decorator_list", None):
            return node.decorator_list[0].lineno
        return node.lineno

    body = tree.body
    for idx, node in enumerate(body):
        name = node_name(node)
        start = seg_start(node)
        end = node.end_lineno  # type: ignore[attr-defined]
        segment = "".join(lines[start - 1 : end])

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_lines.append(segment)
            continue

        if name is None:
            unclassified.append(("<no-name>", segment[:80]))
            continue

        dom = classify(name)
        if dom == "UNCLASSIFIED":
            unclassified.append((name, segment[:80]))
            continue
        domains[dom].append(segment)

    # Report
    print("=== IMPORT BLOCK ===")
    print("".join(import_lines).rstrip() or "(none)")
    print()
    for dom, segs in domains.items():
        # count classes/funcs by re-parsing names
        names = []
        for seg in segs:
            try:
                sub = ast.parse(seg.lstrip())
                for n in sub.body:
                    nm = node_name(n)
                    if nm:
                        names.append(nm)
            except SyntaxError:
                names.append("<decorated>")
        print(f"=== {dom}: {len(segs)} top-level symbols ===")
        print(", ".join(names))
        print()

    if unclassified:
        print("=== !!! UNCLASSIFIED (must be zero before write) !!! ===")
        for nm, preview in unclassified:
            print(f"  {nm}: {preview!r}")
        print()
    else:
        print("=== UNCLASSIFIED: none (safe) ===")

    if not args.write:
        print("\n[dry-run] no files written. re-run with --write to materialize.")
        return

    if unclassified:
        raise SystemExit("refusing to write: unclassified symbols present")

    import_block = "".join(import_lines).rstrip()

    # Per-domain dependency imports (topological: base < module_io < async_chunk < custom_loader; federation independent).
    # Each domain file re-creates the original module-level imports, plus intra-package deps.
    DEP_IMPORTS = {
        "base": "",
        "module_io": "from reverse_deepagent.browser.hooks.module_hooks.base import (\n"
                     "    JS_IDENTIFIER_RE, JS_DOTTED_PATH_RE,\n"
                     "    _module_call_path, _export_access_path, _module_export_hook_path,\n"
                     "    _first_dict, _list_dicts, _string_list, _clip,\n"
                     ")\n",
        "async_chunk": "from reverse_deepagent.browser.hooks.module_hooks.base import (\n"
                       "    JS_IDENTIFIER_RE, JS_DOTTED_PATH_RE,\n"
                       "    _module_call_path, _export_access_path, _module_export_hook_path,\n"
                       "    _first_dict, _list_dicts, _string_list, _clip,\n"
                       ")\n"
                       "from reverse_deepagent.browser.hooks.module_hooks.module_io import (\n"
                       "    ModuleHookSpec, ModuleHookResult, ModuleDiscoveryManager, ModuleHookManager,\n"
                       ")\n",
        "federation": "from reverse_deepagent.browser.hooks.module_hooks.base import (\n"
                      "    JS_IDENTIFIER_RE, JS_DOTTED_PATH_RE,\n"
                      "    _module_call_path, _export_access_path, _module_export_hook_path,\n"
                      "    _first_dict, _list_dicts, _string_list, _clip,\n"
                      ")\n",
        "custom_loader": "from reverse_deepagent.browser.hooks.module_hooks.base import (\n"
                         "    JS_IDENTIFIER_RE, JS_DOTTED_PATH_RE,\n"
                         "    _module_call_path, _export_access_path, _module_export_hook_path,\n"
                         "    _first_dict, _list_dicts, _string_list, _clip,\n"
                         ")\n"
                         "from reverse_deepagent.browser.hooks.module_hooks.module_io import (\n"
                         "    ModuleHookSpec, ModuleHookResult, ModuleDiscoveryManager, ModuleHookManager,\n"
                         ")\n"
                         "from reverse_deepagent.browser.hooks.module_hooks.async_chunk import (\n"
                         "    AsyncChunkModuleDiffManager, AsyncChunkModuleDiffSpec,\n"
                         ")\n",
    }

    pkg = HOOKS / "module_hooks"
    pkg.mkdir(exist_ok=True)

    header = "from __future__ import annotations\n\nimport json\nimport re\nfrom dataclasses import dataclass, field\nfrom typing import Any\n\nfrom reverse_deepagent.browser.base import BrowserPage\nfrom reverse_deepagent.browser.collectors.scripts import ScriptCollector\n"

    DOMAIN_ORDER = ["base", "module_io", "async_chunk", "federation", "custom_loader"]
    collected: dict[str, list[str]] = {}
    for dom in DOMAIN_ORDER:
        segs = domains[dom]
        body_text = "\n\n".join(seg.rstrip() for seg in segs) + "\n"
        dep = DEP_IMPORTS[dom]
        parts = [f'"""module_hooks.{dom} — split from monolithic module_hooks.py (B1 consolidation)."""', "", header]
        if dep:
            parts.append(dep)
        parts.append("")
        parts.append(body_text)
        (pkg / f"{dom}.py").write_text("\n".join(parts), encoding="utf-8")
        # collect exported names for __init__
        names = []
        for seg in segs:
            sub = ast.parse(seg.lstrip())
            for n in sub.body:
                nm = node_name(n)
                if nm and not nm.startswith("_") and not nm.isupper():
                    names.append(nm)
            # capture decorated dataclasses whose seg starts with @
        collected[dom] = names

    # Build __init__.py shim re-exporting public symbols in original order.
    init_lines = ['"""module_hooks package — re-export shim preserving the original flat import contract.', "",
                  "Physical split into base/module_io/async_chunk/federation/custom_loader (B1).",
                  "Public class names and `from ...module_hooks import (...)` paths are unchanged.",
                  '"""', "", "from __future__ import annotations", ""]
    for dom in DOMAIN_ORDER:
        names = collected[dom]
        if not names:
            continue
        init_lines.append(f"from reverse_deepagent.browser.hooks.module_hooks.{dom} import (")
        for nm in names:
            init_lines.append(f"    {nm},")
        init_lines.append(")")
    init_lines.append("")
    init_lines.append("__all__ = [")
    for dom in DOMAIN_ORDER:
        for nm in collected[dom]:
            init_lines.append(f'    "{nm}",')
    init_lines.append("]")
    init_lines.append("")
    (pkg / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")

    print("=== WROTE ===")
    for dom in DOMAIN_ORDER:
        print(f"  module_hooks/{dom}.py : {len(collected[dom])} public symbols")
    print(f"  module_hooks/__init__.py : shim")


if __name__ == "__main__":
    main()
