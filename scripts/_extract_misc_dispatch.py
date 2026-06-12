"""B3a: Surgically extract the 10 'misc' branches from apply_minimal_protection
into _dispatch_misc. No fallback code is touched. No method signature changes.

Strategy:
- Find each misc if-block by guard name
- Build _dispatch_misc method containing those branches
- Replace those if-blocks in apply_minimal_protection with a single dispatch call
- Append _dispatch_misc right after apply_minimal_protection
"""
from __future__ import annotations
import ast, re, hashlib
from pathlib import Path

SRC = Path("src/reverse_deepagent/adapters/native_web.py")

MISC_GUARDS = {
    "flow_timeline",
    "mutation_observer_timeline",
    "runtime_object_graph_diff",
    "object_root_mutation_audit",
    "object_graph_diff",
    "page_mutation_audit",
    "bundler_symbol_scope",
    "function_hook",
    "recursive_continuation_readiness",
    "breakpoint",
}

def find_apply_method(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "NativeWebRuntime":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "apply_minimal_protection":
                    return child
    raise RuntimeError("apply_minimal_protection not found")

def guard_name(stmt):
    """Extract guard name from `if self._is_X_request(...)` statement."""
    if not isinstance(stmt, ast.If):
        return None
    test = stmt.test
    if not (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute)):
        return None
    attr = test.func.attr
    name = re.sub(r"^_is_", "", attr)
    name = re.sub(r"_request$", "", name)
    return name

def main():
    raw = SRC.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    tree = ast.parse(raw)
    method = find_apply_method(tree)

    # Find misc branches in order
    misc_branches = []
    for stmt in method.body:
        gn = guard_name(stmt)
        if gn in MISC_GUARDS:
            misc_branches.append((gn, stmt.lineno, stmt.end_lineno))

    print(f"Found {len(misc_branches)} misc branches:")
    for gn, s, e in misc_branches:
        print(f"  L{s}-L{e}: {gn}")

    if len(misc_branches) != 10:
        print("ERROR: expected 10 misc branches")
        return

    # Build _dispatch_misc body: copy each branch's source lines
    # Each branch is already indented 8 spaces (inside a method inside a class)
    dispatch_lines = []
    dispatch_lines.append("    def _dispatch_misc(self, protection_name: str, context: dict) -> \"ProtectionResult | None\":\n")
    for gn, start, end in misc_branches:
        for ln in lines[start-1:end]:
            dispatch_lines.append(ln)
    dispatch_lines.append("        return None\n")

    # Build replacement for misc branches in apply_minimal_protection:
    # Replace all 10 if-blocks with a single dispatch call
    # Find the line range to replace: from first misc branch to last misc branch
    first_start = misc_branches[0][1]
    last_end = misc_branches[-1][2]

    # Check if misc branches are contiguous (no non-misc branches between them)
    # Get all if-branches in order
    all_branches = []
    for stmt in method.body:
        gn = guard_name(stmt)
        if gn is not None:
            all_branches.append((gn, stmt.lineno, stmt.end_lineno))

    # Find positions of misc branches in the full list
    misc_indices = [i for i,(gn,s,e) in enumerate(all_branches) if gn in MISC_GUARDS]
    print(f"\nMisc branch indices in full branch list: {misc_indices}")

    # Check contiguity
    contiguous = all(misc_indices[i]+1 == misc_indices[i+1] for i in range(len(misc_indices)-1))
    print(f"Contiguous: {contiguous}")

    if not contiguous:
        print("WARNING: misc branches are not contiguous — using scattered replacement")
        # For scattered replacement: replace each misc branch individually
        # Process in reverse order to preserve line numbers
        result_lines = list(lines)
        replacement_inserted = False
        for gn, start, end in reversed(misc_branches):
            if not replacement_inserted:
                # Replace last misc branch with dispatch call + return None check
                repl = [
                    "        # dispatch misc domain\n",
                    "        _misc_result = self._dispatch_misc(protection_name, context)\n",
                    "        if _misc_result is not None:\n",
                    "            return _misc_result\n",
                ]
                result_lines[start-1:end] = repl
                replacement_inserted = True
            else:
                # Delete this branch
                result_lines[start-1:end] = []
    else:
        # All misc branches are contiguous — simple range replacement
        result_lines = list(lines)
        repl = [
            "        # dispatch misc domain\n",
            "        _misc_result = self._dispatch_misc(protection_name, context)\n",
            "        if _misc_result is not None:\n",
            "            return _misc_result\n",
        ]
        result_lines[first_start-1:last_end] = repl

    # Insert _dispatch_misc after apply_minimal_protection
    # Find method end in the modified file by re-parsing
    new_raw = "".join(result_lines)
    new_tree = ast.parse(new_raw)
    new_method = find_apply_method(new_tree)
    insert_after = new_method.end_lineno  # 1-based

    result_lines2 = new_raw.splitlines(keepends=True)
    result_lines2 = result_lines2[:insert_after] + ["\n"] + dispatch_lines + result_lines2[insert_after:]

    # Verify parseable
    final = "".join(result_lines2)
    try:
        ast.parse(final)
        print("\nAST parse: OK")
    except SyntaxError as e:
        print(f"\nAST parse ERROR: {e}")
        return

    # Backup and write
    backup = SRC.parent / "_native_web_b3a_backup.py"
    backup.write_text(raw, encoding="utf-8")
    md5 = hashlib.md5(raw.encode()).hexdigest()
    print(f"Backup: {backup}  md5={md5}")

    SRC.write_text(final, encoding="utf-8")
    orig_lines = len(lines)
    new_line_count = final.count("\n")
    print(f"Written: {SRC}  ({new_line_count} lines, was {orig_lines})")

if __name__ == "__main__":
    main()
