"""B3: Extract apply_minimal_protection branches into domain dispatch methods.

Each branch in apply_minimal_protection is a self-contained if...return block.
We group branches by domain prefix and extract each group into a private method
`_dispatch_<domain>(self, protection_name, context) -> ProtectionResult | None`.

The main method becomes a short loop over domain dispatchers.

Run --dry-run first, then --write.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import re
from pathlib import Path

SRC = Path("src/reverse_deepagent/adapters/native_web.py")

# Domain classification by _is_*_request name keyword prefix
DOMAIN_ORDER = [
    "closure",
    "heap",
    "source",
    "paused",
    "async_chunk",
    "custom_loader",
    "module",
    "misc",  # everything else
]

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "closure":      ["closure_wrapper", "closure_scope"],
    "heap":         ["heap_snapshot"],
    "source":       ["source_map", "bundler_symbol"],
    "paused":       ["paused_session"],
    "async_chunk":  ["async_chunk"],
    "custom_loader":["custom_loader"],
    "module":       ["module_federation", "module_discovery", "module_hook"],
    "misc":         [],   # catch-all
}


def classify_branch(guard_name: str) -> str:
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if domain == "misc":
            continue
        for kw in keywords:
            if kw in guard_name:
                return domain
    return "misc"


def find_apply_method(tree: ast.Module) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "NativeWebRuntime":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "apply_minimal_protection":
                    return child
    raise RuntimeError("apply_minimal_protection not found")


def extract_branches(method: ast.FunctionDef, lines: list[str]) -> list[tuple[str, str, int, int]]:
    """Return list of (guard_name, domain, start_line_1based, end_line_1based)."""
    branches = []
    body = method.body
    # body[0] is `context = context or {}` assignment
    # remaining body items are if-blocks (each starting with if self._is_*_request)
    for stmt in body[1:]:
        if not isinstance(stmt, ast.If):
            continue
        # Extract the guard name from the test expression
        test = stmt.test
        if not (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute)):
            continue
        guard_method = test.func.attr  # e.g. _is_closure_wrapper_runtime_mutability_preflight_request
        # strip leading _is_ and trailing _request
        guard_name = re.sub(r"^_is_", "", guard_method)
        guard_name = re.sub(r"_request$", "", guard_name)
        domain = classify_branch(guard_name)
        start = stmt.lineno
        end = stmt.end_lineno
        # Check for decorator / preceding @staticmethod — not applicable to if blocks
        branches.append((guard_name, domain, start, end))
    return branches


def build_dispatch_method_source(
    domain: str,
    branches: list[tuple[str, str, int, int]],
    lines: list[str],
    indent: str = "    ",
) -> str:
    """Build the source of _dispatch_<domain> method."""
    inner_indent = indent + "    "
    # Method signature
    sig = f"{indent}def _dispatch_{domain}(self, protection_name: str, context: dict) -> \"ProtectionResult | None\":"
    body_lines = [sig]
    for guard_name, _domain, start, end in branches:
        seg = lines[start - 1 : end]
        # seg is already indented with 8 spaces (inside class method)
        # we need to keep it exactly as-is (same indentation level)
        for line in seg:
            body_lines.append(line.rstrip("\n"))
    body_lines.append(f"{inner_indent}return None")
    return "\n".join(body_lines) + "\n"


def build_main_method_source(
    method: ast.FunctionDef,
    lines: list[str],
    domains_present: list[str],
    indent: str = "    ",
) -> str:
    """Build the replacement apply_minimal_protection source."""
    inner = indent + "    "
    inner2 = inner + "    "
    sig_lines = []
    # Reconstruct original signature (lines up to and including the def line)
    for i in range(method.lineno - 1, method.body[0].lineno - 1):
        sig_lines.append(lines[i].rstrip("\n"))

    body = ["\n".join(sig_lines)]
    body.append(f"{inner}context = context or {{}}")
    body.append(f"{inner}_dispatchers = [")
    for dom in domains_present:
        body.append(f"{inner2}self._dispatch_{dom},")
    body.append(f"{inner}]")
    body.append(f"{inner}for _dispatch in _dispatchers:")
    body.append(f"{inner2}_result = _dispatch(protection_name, context)")
    body.append(f"{inner2}if _result is not None:")
    body.append(f"{inner2}    return _result")
    # Preserve original fallback return (last stmt of original method body)
    last_stmt = method.body[-1]
    fallback_lines = lines[last_stmt.lineno - 1 : last_stmt.end_lineno]
    body.append(f"{inner}# fallback (no branch matched)")
    for fl in fallback_lines:
        body.append(fl.rstrip("\n"))
    return "\n".join(body) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    raw = SRC.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=False)
    # Add empty string sentinel so 1-based indexing works cleanly
    lines_1based = [""] + lines  # lines_1based[n] == original line n

    tree = ast.parse(raw)
    method = find_apply_method(tree)

    branches = extract_branches(method, lines_1based)

    # Group by domain preserving order-of-first-appearance
    from collections import defaultdict
    domain_branches: dict[str, list] = defaultdict(list)
    for b in branches:
        domain_branches[b[1]].append(b)

    present_domains = [d for d in DOMAIN_ORDER if d in domain_branches]

    print(f"Total branches: {len(branches)}")
    for dom in present_domains:
        print(f"  {dom}: {len(domain_branches[dom])} branches")

    if args.write:
        # Build new file:
        # 1. Everything before apply_minimal_protection body start
        # 2. New apply_minimal_protection (short dispatcher)
        # 3. The _dispatch_<domain> methods (inserted right after the method)
        # 4. Everything after apply_minimal_protection

        method_start = method.lineno       # def line (1-based)
        method_end   = method.end_lineno   # last line (1-based)

        before = lines[:method_start - 1]   # 0-based slicing: lines before method
        after  = lines[method_end:]         # lines after method

        new_main = build_main_method_source(method, lines_1based, present_domains)

        dispatch_methods = []
        for dom in present_domains:
            dm_src = build_dispatch_method_source(dom, domain_branches[dom], lines_1based)
            dispatch_methods.append(dm_src)

        new_content = (
            "\n".join(before) + "\n"
            + new_main + "\n"
            + "\n".join(dispatch_methods)
            + "\n".join(after)
        )

        # Backup
        backup = SRC.parent / "_native_web_dispatch_backup.py"
        backup.write_text(raw, encoding="utf-8")
        md5 = hashlib.md5(raw.encode()).hexdigest()
        print(f"Backup: {backup}  md5={md5}")

        SRC.write_text(new_content, encoding="utf-8")
        new_lines = new_content.count("\n")
        print(f"Rewritten: {SRC}  ({new_lines} lines, was {len(lines)})")
    else:
        print("\n[dry-run] pass --write to materialise")


if __name__ == "__main__":
    main()
