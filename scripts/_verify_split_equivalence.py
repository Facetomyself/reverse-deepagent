"""Strict equivalence check: every top-level symbol in the original
module_hooks.py must have byte-identical source in the split package.

This goes beyond "tests pass" — it proves the physical relocation did not
mutate a single character of any class/function body.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

HOOKS = Path("src/reverse_deepagent/browser/hooks")
ORIGINAL = HOOKS / "module_hooks_pkg" / "_original_backup.py"
PKG = HOOKS / "module_hooks"
DOMAIN_FILES = ["base.py", "module_io.py", "async_chunk.py", "federation.py", "custom_loader.py"]


def symbol_sources(path: Path) -> dict[str, str]:
    """Map top-level symbol name -> its exact source segment (decorators included)."""
    raw = path.read_text(encoding="utf-8")
    tree = ast.parse(raw)
    lines = raw.splitlines(keepends=True)
    out: dict[str, str] = {}

    def name_of(node: ast.stmt) -> str | None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return node.name
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            return node.target.id
        return None

    def seg_start(node: ast.stmt) -> int:
        if getattr(node, "decorator_list", None):
            return node.decorator_list[0].lineno
        return node.lineno

    for node in tree.body:
        nm = name_of(node)
        if nm is None:
            continue
        start = seg_start(node)
        end = node.end_lineno  # type: ignore[attr-defined]
        out[nm] = "".join(lines[start - 1 : end])
    return out


def main() -> None:
    original = symbol_sources(ORIGINAL)
    # imports/regex aside, drop pure import statements that have no name
    print(f"original top-level named symbols: {len(original)}")

    # Gather split symbols across all domain files.
    split: dict[str, tuple[str, str]] = {}  # name -> (domain_file, source)
    collisions: list[str] = []
    for fname in DOMAIN_FILES:
        srcs = symbol_sources(PKG / fname)
        for nm, src in srcs.items():
            if nm in split:
                collisions.append(f"{nm} in both {split[nm][0]} and {fname}")
            split[nm] = (fname, src)

    print(f"split  top-level named symbols: {len(split)}")
    print()

    if collisions:
        print("!!! SYMBOL COLLISIONS (same name in two domain files):")
        for c in collisions:
            print(f"  {c}")
        print()

    orig_names = set(original)
    split_names = set(split)

    missing = orig_names - split_names
    extra = split_names - orig_names

    if missing:
        print(f"!!! MISSING in split ({len(missing)}): {sorted(missing)}")
    if extra:
        print(f"!!! EXTRA in split ({len(extra)}): {sorted(extra)}")

    # Byte-level body comparison for shared names.
    shared = sorted(orig_names & split_names)
    mismatches: list[str] = []
    for nm in shared:
        o = original[nm]
        _, s = split[nm]
        if hashlib.sha256(o.encode()).hexdigest() != hashlib.sha256(s.encode()).hexdigest():
            mismatches.append(nm)

    print(f"shared symbols compared byte-for-byte: {len(shared)}")
    if mismatches:
        print(f"!!! BODY MISMATCH ({len(mismatches)}):")
        for nm in mismatches:
            print(f"  {nm}")
            # show first differing line for diagnosis
            o_lines = original[nm].splitlines()
            s_lines = split[nm][1].splitlines()
            for i, (a, b) in enumerate(zip(o_lines, s_lines)):
                if a != b:
                    print(f"    first diff @line {i}:")
                    print(f"      orig : {a!r}")
                    print(f"      split: {b!r}")
                    break
    else:
        print("ALL shared symbol bodies are BYTE-IDENTICAL.")

    print()
    if not missing and not extra and not mismatches and not collisions:
        print("=== VERDICT: split is a perfect physical relocation. ===")
    else:
        print("=== VERDICT: DISCREPANCY FOUND — do not trust the split yet. ===")


if __name__ == "__main__":
    main()
