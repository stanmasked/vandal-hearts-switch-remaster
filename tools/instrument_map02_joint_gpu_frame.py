#!/usr/bin/env python3
"""Compose the two exact source-pinned MAP02 native probes in ONE C unit.

Produces an opt-in PC GPU debugger combining the bounded GPU primitive/VRAM
journal with a terminal full native BGR555 frame emitted at the DrawOTag
completion boundary. Does not execute the game or authenticate PS1 pixels.
"""
import argparse
from pathlib import Path

from tools.instrument_map02_frame_flush import (
    instrument as frame_instrument, GUARD as FRAME_FLAG,
)
from tools.instrument_map02_gpu_native_events import (
    instrument as gpu_instrument, GUARD as GPU_FLAG,
)
from tools.prepare_map02_pcport import git_blob_sha1
from tools.instrument_map02_gpu_native_events import PINNED_SOURCE

SESSION_CHECK = r'''
#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE) && defined(VH_MAP02_GPU_CAPTURE)
/* Both observers originate from this single source-pinned GPU translation unit.
 * Require a bounded, even number of before/after journal events, matching
 * frame selectors, and at least one complete event. The offline audit must
 * separately verify all persisted files and the last post-draw VRAM bytes.
 * This does NOT protect journal files from outside writers. */
static int VH_Map02JointGpuSessionReady(void)
{
    VH_CaptureInit();
    return vh_capture_init && vh_capture_frame != 0 &&
        vh_capture_frame == (unsigned long)s_drawFrame &&
        vh_capture_seq >= 2u && vh_capture_seq < VH_CAPTURE_LIMIT &&
        (vh_capture_seq % 2u) == 0u;
}
#endif
'''
COMPILE_GUARD = r'''
#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE) && !defined(VH_MAP02_GPU_CAPTURE)
#error "joint MAP02 frame flush requires native GPU journal instrumentation"
#endif
'''
ORIGINAL_GPU_MARKER = '/* ---- GetTPage / GetClut (psx-spx "Texpage Attribute" / "Clut Attribute") */'
FRAME_FUNCTION = "static int vh_frame_pipe_selected;"
RELEASE = "    if (fflush(NULL) != 0)\n        _exit(93);"


def instrument(original: bytes) -> str:
    if not isinstance(original, bytes) or git_blob_sha1(original) != PINNED_SOURCE:
        raise ValueError("joint MAP02 instrumenter requires exact original PC GPU blob")
    # Each original probe injects into different source anchors; compose
    # the unmodified pinned byte input once, then its GPU observer.
    combined = gpu_instrument(frame_instrument(original))
    for anchor in (FRAME_FUNCTION, ORIGINAL_GPU_MARKER, RELEASE):
        if combined.count(anchor) != 1:
            raise ValueError("joint MAP02 private GPU hook anchor changed")
    combined = combined.replace(
        FRAME_FUNCTION, "static int VH_Map02JointGpuSessionReady(void);\n" +
        FRAME_FUNCTION, 1)
    combined = combined.replace(
        RELEASE,
        "    if (!VH_Map02JointGpuSessionReady())\n"
        "        _exit(96);\n" + RELEASE, 1)
    combined = combined.replace(
        ORIGINAL_GPU_MARKER, SESSION_CHECK + "\n" + ORIGINAL_GPU_MARKER, 1)
    return COMPILE_GUARD + "\n" + combined


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        original = args.source.read_bytes()
        generated = instrument(original)
        if args.source.absolute() == args.output.absolute():
            raise ValueError("cannot overwrite pinned upstream GPU source")
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(generated)
    except (OSError, ValueError, UnicodeError) as exc:
        p.error(str(exc))
    print("Combined source-pinned PC GPU observer generated; no gameplay captured")


if __name__ == "__main__":
    main()
