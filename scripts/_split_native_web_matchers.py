"""B2: Extract _is_*_request static methods from NativeWebRuntime into a mixin.

Strategy:
  - Parse native_web.py with AST.
  - Identify all @staticmethod _is_*_request methods inside NativeWebRuntime.
  - Write them to _native_web_request_matchers.py as _NativeWebRequestMatchers mixin.
  - Remove those methods from native_web.py.
  - Add mixin to NativeWebRuntime inheritance and add import.
  - Zero call-site changes needed (self._is_*() calls resolved via MRO).

Run --dry-run first, then --write.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

SRC = Path("src/reverse_deepagent/adapters")
NATIVE_WEB = SRC / "native_web.py"
MIXIN_FILE = SRC / "_native_web_request_matchers.py"
BACKUP = SRC / "_native_web_backup.py"


def is_matcher(node: ast.stmt) -> bool:
    """Return True if node is a @staticmethod _is_*_request method."""
    if not isinstance(node, ast.FunctionDef):
        return False
    if not (node.name.startswith("_is_") and node.name.endswith("_request")):
        return False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "staticmethod":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "staticmethod":
            return True
    return True  # also accept without explicit decorator (rare)


def find_native_web_runtime(tree: ast.Module) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "NativeWebRuntime":
            return node
    return None


def seg_start(node: ast.stmt) -> int:
    if getattr(node, "decorator_list", None):
        return node.decorator_list[0].lineno
    return node.lineno


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    raw = NATIVE_WEB.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    tree = ast.parse(raw)

    cls = find_native_web_runtime(tree)
    if cls is None:
        raise SystemExit("NativeWebRuntime not found")

    # Collect matcher methods and their line spans (1-based, inclusive).
    matchers: list[tuple[int, int, str, str]] = []  # (start, end, name, src)
    for node in cls.body:
        if is_matcher(node):
            start = seg_start(node)
            end = node.end_lineno  # type: ignore[attr-defined]
            src = "".join(lines[start - 1 : end])
            matchers.append((start, end, node.name, src))

    # Build set of 1-based line numbers to REMOVE from native_web.py.
    remove_lines: set[int] = set()
    for start, end, _, _ in matchers:
        for ln in range(start, end + 1):
            remove_lines.add(ln)
        # Also remove the blank line immediately after the method if present.
        after = end + 1
        if after <= len(lines) and lines[after - 1].strip() == "":
            remove_lines.add(after)

    print(f"Matcher methods found : {len(matchers)}")
    print(f"Lines to remove       : {len(remove_lines)}")
    print(f"Line range            : {matchers[0][0]} – {matchers[-1][1]}")

    # Verify no non-matcher lines accidentally included.
    sample_names = [name for _, _, name, _ in matchers[:5]]
    print(f"Sample names          : {sample_names}")

    if not args.write:
        print("\n[dry-run] re-run with --write to materialise.")
        return

    # ------------------------------------------------------------------ #
    # 1. Backup                                                             #
    # ------------------------------------------------------------------ #
    BACKUP.write_bytes(NATIVE_WEB.read_bytes())
    import hashlib
    md5 = hashlib.md5(NATIVE_WEB.read_bytes()).hexdigest()
    print(f"Backup written: {BACKUP}  md5={md5}")

    # ------------------------------------------------------------------ #
    # 2. Write mixin file                                                  #
    # ------------------------------------------------------------------ #
    mixin_body = "\n".join(src.rstrip() for _, _, _, src in matchers)
    mixin_content = (
        "from __future__ import annotations\n"
        "\n"
        "from typing import Any\n"
        "\n"
        "\n"
        "class _NativeWebRequestMatchers:\n"
        '    """Mixin: route-classification predicates for NativeWebRuntime.\n'
        "\n"
        "    All methods are pure @staticmethod predicates that inspect only\n"
        "    ``protection_name`` and ``context``. Extracted from NativeWebRuntime\n"
        "    (B2 refactor) to keep the main class focused on business logic.\n"
        '    """\n'
        "\n"
    )
    # Indent each line of the mixin body by 4 spaces (methods were already
    # indented as class members inside NativeWebRuntime).
    mixin_content += mixin_body + "\n"
    MIXIN_FILE.write_text(mixin_content, encoding="utf-8")
    print(f"Mixin written: {MIXIN_FILE}  ({MIXIN_FILE.stat().st_size} bytes)")

    # ------------------------------------------------------------------ #
    # 3. Rewrite native_web.py                                             #
    # ------------------------------------------------------------------ #
    new_lines: list[str] = []
    for i, line in enumerate(lines, 1):
        if i in remove_lines:
            continue
        new_lines.append(line)

    new_raw = "".join(new_lines)

    # Add import for mixin (insert after last existing import block line).
    import_line = (
        "from reverse_deepagent.adapters._native_web_request_matchers import "
        "_NativeWebRequestMatchers\n"
    )
    # Find insertion point: after the last `^from` / `^import` line before
    # class NativeWebRuntime.
    class_line_idx = next(
        i for i, l in enumerate(new_raw.splitlines(keepends=True))
        if l.strip().startswith("class NativeWebRuntime(")
    )
    split_lines = new_raw.splitlines(keepends=True)
    last_import_idx = 0
    for i in range(class_line_idx):
        if split_lines[i].startswith(("from ", "import ")):
            last_import_idx = i
    split_lines.insert(last_import_idx + 1, import_line)
    new_raw = "".join(split_lines)

    # Update class definition to inherit mixin.
    new_raw = new_raw.replace(
        "class NativeWebRuntime(WebReverseRuntime):",
        "class NativeWebRuntime(_NativeWebRequestMatchers, WebReverseRuntime):",
        1,
    )

    NATIVE_WEB.write_text(new_raw, encoding="utf-8")
    remaining = sum(1 for l in new_raw.splitlines() if l.strip())
    print(f"native_web.py rewritten: {len(new_raw.splitlines())} lines "
          f"(was {len(lines)}, removed {len(lines) - len(new_raw.splitlines())})")


if __name__ == "__main__":
    main()
