#!/usr/bin/env python3
"""Create a compile-time-exclusive Switch present branch in pinned PC_GpuPresent.

The output is a generated source file; the upstream file is not modified.
The Switch callback owns the sole upload/draw/swap. The original desktop tail
remains byte-for-byte unchanged in the alternative branch.
"""
import argparse
from pathlib import Path

START = "    /* Scale the native w*h framebuffer up to fill the current window, preserving"
END = "    if (s_ptTime) {\n        pt3 = presentNowMs();"
SWITCH_CALL = """#if defined(VH_SWITCH_EXCLUSIVE_PRESENT)
    /* Post-composition, borrowed bottom-up RGB24; callback owns the only swap. */
    extern void VH_ObserveCompletedRGB24(const unsigned char *pixels,
                                          size_t capacity, int width, int height);
    if (s_rgbaScratch && w > 0 && h > 0 && s_scratchCap > 0 &&
        (size_t)w <= ((size_t)s_scratchCap / 3u) / (size_t)h) {
        VH_ObserveCompletedRGB24(s_rgbaScratch, (size_t)s_scratchCap, w, h);
    }
#else
"""

def patch(source: str) -> str:
    if "VH_SWITCH_EXCLUSIVE_PRESENT" in source or "VH_SWITCH_OBSERVER_BEGIN" in source:
        raise ValueError("already instrumented or conflicting observer enabled")
    if "void PC_GpuPresent(unsigned short *vram" not in source:
        raise ValueError("unexpected upstream implementation")
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("expected unique pinned upstream presentation tail")
    if source.count("SDL_GL_SwapWindow(s_window);") != 1:
        raise ValueError("expected one desktop GL swap")
    start = source.index(START)
    end = source.index(END, start)
    tail = source[start:end]
    if "glDrawPixels(" not in tail or "SDL_GL_SwapWindow(s_window);" not in tail:
        raise ValueError("desktop draw/swap must be in the selected tail")
    return source[:start] + SWITCH_CALL + tail + "#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */\n" + source[end:]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    output = patch(args.source.read_text(encoding="utf-8"))
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(output, encoding="utf-8")

if __name__ == "__main__":
    main()
