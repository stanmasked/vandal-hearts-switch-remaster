#!/usr/bin/env python3
"""Add an optional read-only completed RGB24 observer to pinned PC_GpuPresent.

The upstream SDL renderer is left untouched by default. This is a temporary
verification seam, NOT the libnx backend or a replacement for SDL's swap.
"""
import argparse
from pathlib import Path

ANCHOR = "    if (PC_OverlayIsOpen()) PC_GpuDrawOverlay(w, h);   /* options overlay, on top */"
WINDOW_GUARD = "#if defined(__APPLE__)\n    if (!s_window || !s_renderer) return; /* headless: no-op */\n#else\n    if (!s_window || !s_glCtx) return; /* headless: no-op */\n#endif"
TARGET_WINDOW_GUARD = "#if !defined(VH_SWITCH_EXCLUSIVE_PRESENT)\n" + WINDOW_GUARD + "\n#endif /* desktop-only window prerequisite */"
EVENT_PUMP = "    PC_GpuPumpEvents();"
TARGET_EVENT_PUMP = """#if !defined(VH_SWITCH_EXCLUSIVE_PRESENT)
    PC_GpuPumpEvents();
#endif /* external Switch event loop owns SDL pumping */"""
BEGIN = "    /* VH_SWITCH_OBSERVER_BEGIN: post-composition RGB24 boundary */"
END = "    /* VH_SWITCH_OBSERVER_END */"
INSERT = """    /* VH_SWITCH_OBSERVER_BEGIN: post-composition RGB24 boundary */
#if defined(VH_SWITCH_EXCLUSIVE_PRESENT) && !defined(VH_SWITCH_COMPLETED_FRAME_OBSERVER)
#error VH_SWITCH_EXCLUSIVE_PRESENT requires VH_SWITCH_COMPLETED_FRAME_OBSERVER
#endif
#if defined(VH_SWITCH_COMPLETED_FRAME_OBSERVER)
    /*
     * Borrowed, packed bottom-up RGB24. Only consume synchronously.
     * s_scratchCap is the actual capacity in this pinned upstream version.
     * DO NOT keep the pointer; the next present can free/reallocate it.
     */
    extern void VH_ObserveCompletedRGB24(const unsigned char *pixels,
                                          size_t capacity, int width, int height);
    /* Validate the actual allocation without multiplying untrusted ints. */
    if (s_rgbaScratch && w > 0 && h > 0 && s_scratchCap > 0 &&
        (size_t)w <= ((size_t)s_scratchCap / 3u) / (size_t)h) {
        VH_ObserveCompletedRGB24(s_rgbaScratch, (size_t)s_scratchCap, w, h);
    }
#endif
    /* VH_SWITCH_OBSERVER_END */
#if defined(VH_SWITCH_EXCLUSIVE_PRESENT)
    /* Target owns frame presentation: bypass desktop draw and swap. */
    return;
#endif"""


def patch(source: str) -> str:
    if BEGIN in source or END in source:
        raise ValueError("already instrumented; refusing duplicate injection")
    if source.count(ANCHOR) != 1:
        raise ValueError("expected precisely one pinned upstream overlay anchor")
    if "void PC_GpuPresent(unsigned short *vram" not in source:
        raise ValueError("not the pinned upstream presentation implementation")
    if "SDL_GL_SwapWindow(s_window);" not in source:
        raise ValueError("desktop presentation tail not found")
    if source.count(WINDOW_GUARD) != 1:
        raise ValueError("expected precisely one desktop window guard")
    if source.count(EVENT_PUMP) != 1:
        raise ValueError("expected precisely one desktop SDL event pump")
    return (source.replace(WINDOW_GUARD, TARGET_WINDOW_GUARD, 1)
            .replace(EVENT_PUMP, TARGET_EVENT_PUMP, 1)
            .replace(ANCHOR, ANCHOR + "\n\n" + INSERT, 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = patch(args.source.read_text(encoding="utf-8"))
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(result, encoding="utf-8")


if __name__ == "__main__":
    main()
