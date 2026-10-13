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
ADDRESS = re.compile(r"(?i)(?<![\w])(?:0x)?(800[0-7][0-9a-f]{4}|1f800[0-9a-f]{3}|1f801[0-9a-f]{3}|00000000)(?![\w])")
# Match the documented PS1 main RAM, scratchpad, I/O-register range, and NULL mirror.
# Some code uses shortened or macro-based addresses that this deliberately simple scan misses.

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
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            for match in ADDRESS.finditer(line):
                value = match.group(1).lower()
                if value.startswith("800"):
                    kind = "main-RAM"
                elif value.startswith("1f800"):
                    kind = "scratchpad"
                elif value.startswith("1f801"):
                    kind = "I/O-register-range"
                else:
                    kind = "NULL-mirror-or-zero"
                hits.append((kind, path.relative_to(ROOT).as_posix(), number, line.strip()[:220], value))

    print(f"PS1 guest-address literal inventory: {len(files)} source files scanned under {ROOT}")
    print("Scope: src/, platform/pc/src/, platform/pc/include/; comments and inactive #if branches are included.")
    print("This is a literal-pattern inventory only: it is not a complete semantic or pointer-flow analysis.")
    groups = ("main-RAM", "scratchpad", "I/O-register-range", "NULL-mirror-or-zero")
    for group in groups:
        rows = [row for row in hits if row[0] == group]
        print(f"\n[{group}] {len(rows)} occurrence(s)")
        for _, path, number, source, value in rows:
            print(f"  {path}:{number}: 0x{value} | {source}")
    print("\nReview each occurrence for dereference, offset arithmetic, stored guest pointer, I/O access, or documentation-only use.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
