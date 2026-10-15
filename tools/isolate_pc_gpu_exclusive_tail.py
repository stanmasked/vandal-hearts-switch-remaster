#!/usr/bin/env python3
"""Extract the actual pinned PC_GpuPresent backend seam as a standalone C TU.

This compiles the exact source-derived presentation *tail*, not the full
upstream module or game. The switch define must remove desktop OpenGL.
"""
import argparse
from pathlib import Path

START = "#if defined(VH_SWITCH_EXCLUSIVE_PRESENT)"
END = "#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */"

def isolate(patched: str) -> str:
    if patched.count(START) != 1 or patched.count(END) != 1:
        raise ValueError("expected exactly one exclusive present seam")
    begin = patched.index(START)
    finish = patched.index(END, begin) + len(END)
    fragment = patched[begin:finish]
    if "SDL_GL_SwapWindow" not in fragment or "VH_ObserveCompletedRGB24" not in fragment:
        raise ValueError("source must preserve both backends")
    return (
        "#include <stddef.h>\n"
        '#include "switch_upstream_observer.h"\n'
        "static unsigned char *s_rgbaScratch;\n"
        "static int s_scratchCap;\n"
        "void vh_compile_check_upstream_present_tail(int w, int h) {\n"
        "    int s_ptTime = 0;\n"
        "    double pt2 = 0;\n"
        "    (void)pt2;\n"
        "    (void)s_ptTime;\n"
        + fragment + "\n"
        "}\n"
    )

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patched_source", type=Path)
    parser.add_argument("output_c", type=Path)
    args = parser.parse_args()
    generated = isolate(args.patched_source.read_text(encoding="utf-8"))
    args.output_c.parent.mkdir(parents=True, exist_ok=True)
    args.output_c.write_text(generated, encoding="utf-8")

if __name__ == "__main__":
    main()
