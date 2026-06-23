"""B3c: Extract source and paused domain branches from apply_minimal_protection."""
from __future__ import annotations
import ast, re, hashlib
from pathlib import Path

SRC = Path("src/reverse_deepagent/adapters/native_web.py")

SOURCE_KEYWORDS = [
    "source_map", "bundler_symbol", "source_map_fetch",
]
PAUSED_KEYWORDS = ["paused_session"]

def classify(guard: str) -> str:
    for kw in SOURCE_KEYWORDS:
        if kw in guard: return "source"
    for kw in PAUSED_KEYWORDS:
        if kw in guard: return "paused"
    return "other"

def find_method(tree, cls_name, method_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return child
    raise RuntimeError(f"{method_name} not found")

def main():
    raw = SRC.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=False)
    lines1 = [""] + lines  # 1-based
    tree = ast.parse(raw)
    method = find_method(tree, "NativeWebRuntime", "apply_minimal_protection")

    source_segs, paused_segs = [], []
    for stmt in method.body:
        if not isinstance(stmt, ast.If): continue
        test = stmt.test
        if not (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute)): continue
        guard = test.func.attr  # e.g. _is_source_map_lookup_request
        domain = classify(guard)
        if domain not in ("source", "paused"): continue
        start, end = stmt.lineno, stmt.end_lineno
        seg = "\n".join(lines1[start:end+1])
        if domain == "source": source_segs.append((start, end, seg))
        else: paused_segs.append((start, end, seg))

    print(f"source: {len(source_segs)} branches")
    print(f"paused: {len(paused_segs)} branches")

    # Build dispatch methods (8-space indent inside class, 4-space for method def)
    def build_dispatch(name, segs):
        lines_out = [f"    def _{name}(self, protection_name: str, context: dict) -> \"ProtectionResult | None\":"]
        for _, _, seg in segs:
            for line in seg.splitlines():
                lines_out.append(line)
        lines_out.append("        return None")
        return "\n".join(lines_out) + "\n"

    source_method = build_dispatch("dispatch_source", source_segs)
    paused_method = build_dispatch("dispatch_paused", paused_segs)

    # Replace each branch in the original file with a call to the dispatch method (first branch only — insert call before first source branch)
    # Strategy: replace each if-block with `if (r := self._dispatch_source(...)): return r` style
    # Simpler: collect all line ranges to DELETE, then insert dispatch calls at first occurrence

    # Build new file: delete all source/paused if-blocks, insert dispatch calls at their earliest position
    source_lines = sorted(set(range(source_segs[0][0], source_segs[-1][1]+1)))
    paused_lines = sorted(set(range(paused_segs[0][0], paused_segs[-1][1]+1)))

    # We'll rebuild line by line, skipping extracted ranges but inserting dispatch call at first line
    source_ranges = [(s,e) for s,e,_ in source_segs]
    paused_ranges = [(s,e) for s,e,_ in paused_segs]

    def in_range(lnum, ranges):
        for s,e in ranges:
            if s <= lnum <= e: return True
        return False

    source_first = source_segs[0][0]
    paused_first = paused_segs[0][0]
    source_inserted = False
    paused_inserted = False

    new_lines = []
    for i, line in enumerate(lines, start=1):
        if in_range(i, source_ranges):
            if not source_inserted and i == source_first:
                new_lines.append("        _source_result = self._dispatch_source(protection_name, context)")
                new_lines.append("        if _source_result is not None:")
                new_lines.append("            return _source_result")
                source_inserted = True
            continue
        if in_range(i, paused_ranges):
            if not paused_inserted and i == paused_first:
                new_lines.append("        _paused_result = self._dispatch_paused(protection_name, context)")
                new_lines.append("        if _paused_result is not None:")
                new_lines.append("            return _paused_result")
                paused_inserted = True
            continue
        new_lines.append(line)

    # Find insertion point for dispatch methods: right before `create_native_web_runtime`
    insert_at = None
    for i, line in enumerate(new_lines):
        if "def create_native_web_runtime" in line:
            insert_at = i
            break
    if insert_at is None:
        insert_at = len(new_lines)

    final_lines = new_lines[:insert_at] + [""] + source_method.splitlines() + [""] + paused_method.splitlines() + [""] + new_lines[insert_at:]
    new_content = "\n".join(final_lines)

    # Backup
    backup = SRC.parent / "_native_web_b3c_backup.py"
    backup.write_text(raw, encoding="utf-8")
    md5 = hashlib.md5(raw.encode()).hexdigest()
    print(f"Backup: {backup}  md5={md5}")

    SRC.write_text(new_content, encoding="utf-8")
    print(f"Written: {SRC}  ({new_content.count(chr(10))} lines, was {len(lines)})")

    # Verify AST
    try:
        ast.parse(new_content)
        print("AST parse: OK")
    except SyntaxError as e:
        print(f"AST parse ERROR: {e}")

if __name__ == "__main__":
    main()
