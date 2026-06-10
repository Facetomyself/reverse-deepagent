"""B3b: Extract 22 page-free heap branches from apply_minimal_protection."""
from __future__ import annotations
import ast, re, hashlib, argparse
from pathlib import Path

SRC = Path("src/reverse_deepagent/adapters/native_web.py")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    raw = SRC.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=False)
    tree = ast.parse(raw)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "NativeWebRuntime":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "apply_minimal_protection":
                    method = child

    heap_free = []  # (attr, start_1based, end_1based)
    for stmt in method.body:
        if not isinstance(stmt, ast.If):
            continue
        test = stmt.test
        if not (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute)):
            continue
        attr = test.func.attr
        if "_is_heap_snapshot" not in attr:
            continue
        seg = "\n".join(lines[stmt.lineno - 1 : stmt.end_lineno])
        if re.search(r"\bpage\b", seg):
            print(f"  SKIP (page-using): L{stmt.lineno} {attr}")
            continue
        heap_free.append((attr, stmt.lineno, stmt.end_lineno))

    print(f"Page-free heap branches: {len(heap_free)}")
    for attr, s, e in heap_free:
        print(f"  L{s}-{e}: {attr}")

    if not args.write:
        print("\n[dry-run]")
        return

    # Build _dispatch_heap method source from the 22 branches
    dispatch_lines = ["    def _dispatch_heap(self, protection_name: str, context: dict) -> \"ProtectionResult | None\":"]
    for attr, s, e in heap_free:
        for line in lines[s - 1 : e]:
            dispatch_lines.append(line.rstrip("\n"))
    dispatch_lines.append("        return None")
    dispatch_src = "\n".join(dispatch_lines) + "\n"

    # Replace the 22 if-blocks in the method body with a single dispatcher call.
    # Strategy: find the contiguous block L536..L2115 (22 branches, excluding collect at L6497).
    # They are all contiguous, so replace lines[535..2115] with the call.
    first_start = heap_free[0][1]   # 536
    last_end    = heap_free[-1][2]  # 2115

    call_lines = [
        "        _heap_result = self._dispatch_heap(protection_name, context)",
        "        if _heap_result is not None:",
        "            return _heap_result",
    ]

    before = lines[:first_start - 1]       # 0-indexed, up to line 535
    after  = lines[last_end:]              # from line 2115 onward

    new_body = (
        "\n".join(before) + "\n"
        + "\n".join(call_lines) + "\n"
        + "\n".join(after) + "\n"
    )

    # Append _dispatch_heap method after apply_minimal_protection end
    # Re-parse to find method end in new_body
    new_tree = ast.parse(new_body)
    new_method_end = None
    for node in ast.walk(new_tree):
        if isinstance(node, ast.ClassDef) and node.name == "NativeWebRuntime":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "apply_minimal_protection":
                    new_method_end = child.end_lineno

    new_lines = new_body.splitlines(keepends=False)
    final = (
        "\n".join(new_lines[:new_method_end]) + "\n\n"
        + dispatch_src + "\n"
        + "\n".join(new_lines[new_method_end:]) + "\n"
    )

    backup = SRC.parent / "_native_web_b3b_backup.py"
    backup.write_text(raw, encoding="utf-8")
    md5 = hashlib.md5(raw.encode()).hexdigest()
    print(f"Backup: {backup}  md5={md5}")

    SRC.write_text(final, encoding="utf-8")
    print(f"Written: {SRC}  ({final.count(chr(10))} lines, was {len(lines)})")
    # Verify AST parse
    try:
        ast.parse(final)
        print("AST parse: OK")
    except SyntaxError as e:
        print(f"AST parse ERROR: {e}")

if __name__ == "__main__":
    main()
