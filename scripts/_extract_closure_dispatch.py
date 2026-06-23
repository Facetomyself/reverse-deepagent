"""B3a: Extract closure domain branches from apply_minimal_protection.

Only extracts the 14 closure_wrapper / closure_scope branches (all page-FREE).
Uses line-level surgery: finds each branch via AST, builds _dispatch_closure,
inserts it after apply_minimal_protection, and replaces the 14 if-blocks with
a single dispatch call at the top of the method.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path("src/reverse_deepagent/adapters/native_web.py")

CLOSURE_KEYWORDS = ["closure_wrapper", "closure_scope"]


def is_closure_branch(guard_attr: str) -> bool:
    name = re.sub(r"^_is_", "", guard_attr)
    name = re.sub(r"_request$", "", name)
    return any(kw in name for kw in CLOSURE_KEYWORDS)


def main() -> None:
    raw = SRC.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=False)
    tree = ast.parse(raw)

    # Find apply_minimal_protection
    method: ast.FunctionDef | None = None
    class_node: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "NativeWebRuntime":
            class_node = node
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "apply_minimal_protection":
                    method = child
                    break

    assert method is not None, "apply_minimal_protection not found"
    assert class_node is not None

    # Collect closure branches
    closure_branches: list[tuple[int, int]] = []  # (start_1based, end_1based)
    for stmt in method.body[1:]:  # skip context = context or {}
        if not isinstance(stmt, ast.If):
            continue
        test = stmt.test
        if not (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute)):
            continue
        if is_closure_branch(test.func.attr):
            closure_branches.append((stmt.lineno, stmt.end_lineno))

    print(f"Closure branches found: {len(closure_branches)}")
    for s, e in closure_branches:
        print(f"  L{s}-L{e}")

    assert len(closure_branches) == 14, f"Expected 14, got {len(closure_branches)}"

    # Build _dispatch_closure method source
    # Each branch is already indented with 8 spaces inside the class method.
    # We keep that indentation as-is — they become the body of _dispatch_closure.
    dispatch_lines: list[str] = [
        "    def _dispatch_closure(self, protection_name: str, context: dict) -> \"ProtectionResult | None\":",
    ]
    for start, end in closure_branches:
        for line in lines[start - 1 : end]:
            dispatch_lines.append(line)
    dispatch_lines.append("        return None")
    dispatch_src = "\n".join(dispatch_lines) + "\n"

    # Replacement for the 14 if-blocks inside apply_minimal_protection:
    # Insert `_closure_result = self._dispatch_closure(...); if ...: return`
    # right after `context = context or {}` (method.body[0] line).
    dispatch_call = (
        "        _closure_result = self._dispatch_closure(protection_name, context)\n"
        "        if _closure_result is not None:\n"
        "            return _closure_result\n"
    )

    # Build new file content line by line
    # Step 1: remove the 14 closure if-blocks from the method
    # Step 2: insert dispatch_call after context line
    # Step 3: insert _dispatch_closure method after end of apply_minimal_protection

    remove_ranges: set[int] = set()
    for start, end in closure_branches:
        for ln in range(start, end + 1):
            remove_ranges.add(ln)

    context_line = method.body[0].lineno  # `context = context or {}`
    method_end = method.end_lineno

    new_lines: list[str] = []
    for i, line in enumerate(lines):
        ln = i + 1  # 1-based
        if ln in remove_ranges:
            continue
        new_lines.append(line)
        if ln == context_line:
            # Insert dispatch call right after context = context or {}
            new_lines.extend(dispatch_call.splitlines())
        if ln == method_end:
            # Insert _dispatch_closure method after apply_minimal_protection
            new_lines.append("")
            new_lines.extend(dispatch_src.splitlines())

    new_content = "\n".join(new_lines) + "\n"

    # Verify AST parse
    try:
        ast.parse(new_content)
    except SyntaxError as exc:
        print(f"SYNTAX ERROR after transform: {exc}")
        raise

    SRC.write_text(new_content, encoding="utf-8")
    new_lc = new_content.count("\n")
    print(f"Written: {SRC}  ({new_lc} lines, was {len(lines)})")
    print("AST parse: OK")


if __name__ == "__main__":
    main()
