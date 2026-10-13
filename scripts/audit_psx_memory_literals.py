#!/usr/bin/env python3
"""Inventory PS1 guest-address literals in upstream C/C++ source.

This is a review aid, not a complete pointer/data-flow analysis. It scans source files,
reports address-shaped literals and their surrounding lines, and never modifies upstream.
"""
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/upstream-pc-port")
SCAN_ROOTS = (ROOT / "src", ROOT / "platform/pc/src", ROOT / "platform/pc/include")
SOURCE_SUFFIXES = {".c", ".h", ".cpp", ".hpp", ".inc"}
ADDRESS = re.compile(r"(?i)(?<![\w])(?:0x)?(80[0-7][0-9a-f]{5}|1f800[0-9a-f]{3}|1f801[0-9a-f]{3}|00000000)[uUlL]*(?![\w])")
GROUPS = ("main-RAM", "scratchpad", "I/O-register-range", "NULL-mirror-or-zero")


def mask_comments_and_literals(source: str) -> str:
    """Replace comments and quoted literals with spaces, preserving offsets/newlines."""
    chars = list(source)
    i = 0
    state = "code"
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                chars[i] = chars[i + 1] = " "
                i += 2
                state = "line-comment"
                continue
            if ch == "/" and nxt == "*":
                chars[i] = chars[i + 1] = " "
                i += 2
                state = "block-comment"
                continue
            if ch == '"':
                chars[i] = " "
                i += 1
                state = "string"
                continue
            if ch == "'":
                chars[i] = " "
                i += 1
                state = "char"
                continue
            i += 1
            continue
        if state == "line-comment":
            if ch == "\n":
                state = "code"
            else:
                chars[i] = " "
            i += 1
            continue
        if state == "block-comment":
            if ch == "*" and nxt == "/":
                chars[i] = chars[i + 1] = " "
                i += 2
                state = "code"
            else:
                if ch != "\n":
                    chars[i] = " "
                i += 1
            continue
        # C/C++ string or character literal. Honor escaped quotes and backslashes.
        if ch == "\\":
            chars[i] = " "
            if i + 1 < len(source):
                if source[i + 1] != "\n":
                    chars[i + 1] = " "
                i += 2
            else:
                i += 1
            continue
        if (state == "string" and ch == '"') or (state == "char" and ch == "'"):
            chars[i] = " "
            state = "code"
        elif ch != "\n":
            chars[i] = " "
        i += 1
    return "".join(chars)


def classify(value: str) -> str:
    value = value.lower()
    if value.startswith("80"):
        return "main-RAM"
    if value.startswith("1f800"):
        return "scratchpad"
    if value.startswith("1f801"):
        return "I/O-register-range"
    return "NULL-mirror-or-zero"


def main() -> int:
    files = []
    for root in SCAN_ROOTS:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES)
    if not files:
        print(f"ERROR: no upstream C/C++ sources found beneath {ROOT}", file=sys.stderr)
        return 2

    hits = []
    for path in sorted(set(files)):
        try:
            source_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = source_text.splitlines()
        masked_lines = mask_comments_and_literals(source_text).splitlines()
        relative = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(lines, 1):
            masked_line = masked_lines[number - 1] if number - 1 < len(masked_lines) else ""
            for match in ADDRESS.finditer(line):
                value = match.group(1).lower()
                code_span = masked_line[match.start():match.end()]
                origin = "code" if any(ch.isalnum() for ch in code_span) else "comment/string"
                hits.append((classify(value), origin, relative, number, line.strip()[:220], value))

    print(f"PS1 guest-address literal inventory: {len(files)} source files scanned under {ROOT}")
    print("Scope: src/, platform/pc/src/, platform/pc/include/; raw totals include comments and inactive #if branches.")
    print("Code/comment classification masks C comments and ordinary string/character literals; it is heuristic, not pointer-flow analysis.")
    for group in GROUPS:
        rows = [row for row in hits if row[0] == group]
        code_count = sum(row[1] == "code" for row in rows)
        non_code_count = len(rows) - code_count
        print(f"\n[{group}] {len(rows)} occurrence(s): {code_count} code, {non_code_count} comment/string")
        for _, origin, path, number, source, value in rows:
            print(f"  [{origin}] {path}:{number}: 0x{value} | {source}")
    print("\nReview code-tagged occurrences first; comments, strings, and inactive preprocessor branches still require manual interpretation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
