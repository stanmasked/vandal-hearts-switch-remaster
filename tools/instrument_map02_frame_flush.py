#!/usr/bin/env python3
"""Source-pinned, opt-in native VRAM flush hook for the public PC-port DrawOTag.

This is a one-shot Linux diagnostic copy of libgpu.c, not a patch to the game
or a PS1 pixel-accuracy claim. The full 1024x512 native BGR555 VRAM is emitted
after synchronous native rendering, before presentation; HD buffer is NOT used.
"""
import argparse
from pathlib import Path

from tools.instrument_map02_gpu_native_events import PINNED_SOURCE
from tools.prepare_map02_pcport import git_blob_sha1

GUARD = "VH_MAP02_PRIVATE_FRAME_PIPE_TRACE"
INSERT_AT = "#define VRAM_H 512\n"
CALL_AFTER = ("    PC_MaybeDumpVram(); /* VH_VRAM_DUMP=N: snapshot VRAM "
              "to PPM for texture/CLUT triage */")
CALL = """#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE)
    VH_Map02PrivateFrameFlush();
#endif
"""
HELPER = r'''
#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE)
#include "map02_native_frame_pipe.h"
#include <errno.h>
#include <limits.h>
#include <unistd.h>

/* Frame number is selected by the independent one-shot host launcher.
 * Stop at the FIRST completed DrawOTag matching this number only.
 * Do not place a hook inside the primitive walk or the deferred hires pass.
 * This captures PC native VRAM, not a PS1 console framebuffer. */
static int vh_frame_pipe_selected;
static unsigned long vh_frame_pipe_frame;
static void VH_Map02PrivateFrameFlush(void)
{
    unsigned short (*vram)[VRAM_W];
    const char *value;
    char *end = NULL;
    unsigned long selected;

    if (vh_frame_pipe_selected == 2)
        return;
    if (vh_frame_pipe_selected == 0) {
        vh_frame_pipe_selected = 2;
        value = getenv("VH_MAP02_PRIVATE_FRAME_PIPE_FRAME");
        if (!value || !value[0] || value[0] < '0' || value[0] > '9')
            return;
        errno = 0;
        selected = strtoul(value, &end, 10);
        if (errno != 0 || end == value || !end || *end != '\0' ||
                selected == 0 || selected > 0xffffffffUL)
            return;
        vh_frame_pipe_frame = selected;
        vh_frame_pipe_selected = 1;
    }
    if (vh_frame_pipe_frame != (unsigned long)s_drawFrame)
        return;

    /* Diagnostic capture is a one-shot process, not normal gameplay.
     * Flush stdio journals; any previous stdout bytes intentionally cause
     * the independent binary-only host reader to reject this capture. */
    if (fflush(NULL) != 0)
        _exit(93);
    if (vh_map02_frame_pipe_wait_release(STDIN_FILENO) != 0)
        _exit(94);
    vram = PC_GpuVram();
    if (vh_map02_frame_pipe_emit(STDOUT_FILENO, s_drawFrame,
                                 VRAM_W, VRAM_H, &vram[0][0], VRAM_W) != 0)
        _exit(95);
    /* Complete a single frame and close stdout without later game logging.
     * A private debug build MUST NOT keep playing after this boundary. */
    _exit(0);
}
#endif
'''


def instrument(data: bytes) -> str:
    """Reject anything but the original pinned blob; make one explicit hook."""
    if not isinstance(data, bytes) or git_blob_sha1(data) != PINNED_SOURCE:
        raise ValueError("MAP02 frame flush requires exact pinned original PC GPU")
    source = data.decode("utf-8")
    if GUARD in source:
        raise ValueError("MAP02 frame flush already instrumented")
    if source.count(INSERT_AT) != 1 or source.count(CALL_AFTER) != 1:
        raise ValueError("MAP02 frame flush anchor count changed")
    if source.count("    TrcFrameEnd();") != 1 or source.count("    if (HiresActive()) {") != 1:
        raise ValueError("MAP02 completion / presentation anchors changed")
    if (not source.index("    TrcFrameEnd();") <
            source.index(CALL_AFTER) <
            source.index("    if (HiresActive()) {")):
        raise ValueError("MAP02 hook must be after raster walk, before presentation")
    return (source.replace(INSERT_AT, INSERT_AT + HELPER + "\n", 1)
            .replace(CALL_AFTER, CALL_AFTER + "\n" + CALL, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        before = args.source.read_bytes()
        transformed = instrument(before)
        if args.output.absolute() == args.source.absolute():
            raise ValueError("MAP02 original GPU source must not be overwritten")
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(transformed)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    print("MAP02 source-pinned native frame hook generated; not game evidence")


if __name__ == "__main__":
    main()
