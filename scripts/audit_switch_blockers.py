#!/usr/bin/env python3
"""Report source-level blockers before attempting to compile the desktop backend for Switch.

This is an inventory tool, not a proof of compatibility. It intentionally exits successfully
when known blockers are found; CI uses it to keep the audit visible as the upstream pin changes.
"""
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/upstream-pc-port")
SCAN_ROOTS = (ROOT / "platform/pc/src", ROOT / "platform/pc/include")
RULES = [
    ("fixed-PSX-address", re.compile(r"0x(?:80000000|1f800000|00000000)\b", re.I),
     "Hard-coded PS1 address; requires a Switch-compatible memory model"),
    ("desktop-virtual-memory", re.compile(r"\b(?:mmap|mprotect|munmap|VirtualAlloc|VirtualProtect)\s*\("),
     "Desktop VM API; cannot assume arbitrary fixed-address mappings on Horizon"),
    ("desktop-loader-introspection", re.compile(r"\b(?:Elf(?:32|64)_|IMAGE_NT_HEADERS|_NSGetExecutablePath|ucontext_t|REG_EIP|REG_RIP)\b"),
     "Executable-format or OS-specific introspection"),
    ("SDL-windowing", re.compile(r"#\s*include\s*[<\"]SDL2/|\bSDL_(?:CreateWindow|CreateRenderer|GL_CreateContext|PollEvent)\b"),
     "Desktop SDL window/input path; replace or adapt for libnx"),
    ("desktop-graphics", re.compile(r"#\s*include\s*[<\"]SDL2/SDL_opengl\.h|\bgl(?:Bind|Clear|Draw|Tex|Viewport|Create)\w*\s*\("),
     "Desktop OpenGL presentation path"),
    ("desktop-audio", re.compile(r"#\s*include\s*[<\"]AL/|\b(?:alcOpenDevice|alSourcePlay|SDL_OpenAudio)\s*\("),
     "Desktop audio API; needs a Switch audio backend"),
    ("posix-threading", re.compile(r"\b(?:pthread_create|pthread_join|pthread_mutex_init|pthread_cond_wait)\s*\("),
     "Threading primitive; verify libnx/newlib availability and semantics"),
]

def main() -> int:
    files = []
    for root in SCAN_ROOTS:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix in {".c", ".h", ".cpp", ".hpp"})
    if not files:
        print(f"ERROR: no upstream C/C++ sources found beneath {ROOT}", file=sys.stderr)
        return 2

    hits = {name: [] for name, _, _ in RULES}
    for path in sorted(files):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            for name, pattern, _description in RULES:
                if pattern.search(line):
                    hits[name].append((path.relative_to(ROOT).as_posix(), number, line.strip()[:180]))

    print(f"Switch blocker audit: {len(files)} C/C++ files scanned under {ROOT}")
    for name, _pattern, description in RULES:
        rows = hits[name]
        print(f"\n[{name}] {len(rows)} match(es) — {description}")
        for path, number, source in rows[:12]:
            print(f"  {path}:{number}: {source}")
        if len(rows) > 12:
            print(f"  ... {len(rows) - 12} additional matches omitted")
    print("\nInterpretation: findings are review targets, not all necessarily fatal; no findings does not prove a Switch build.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
