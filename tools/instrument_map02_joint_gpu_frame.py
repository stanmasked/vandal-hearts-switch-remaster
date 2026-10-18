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
        (vh_capture_seq % 2u) == 0u &&
        vh_map02_joint_events_completed == vh_capture_seq;
}
#endif
'''
COMPILE_GUARD = r'''
#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE) && !defined(VH_MAP02_GPU_CAPTURE)
#error "joint MAP02 frame flush requires native GPU journal instrumentation"
#endif
'''

PRIVATE_FILE_OPENERS = (
    '    file = fopen(snapshot_path, "wb");',
    '        file = fopen(upload_path, "wb");',
    '    log = fopen(log_path, "ab");',
    '    fclose(log);',
)
EVENT_ANCHOR = 'static void VH_CaptureEvent('

SECURE_JOURNAL = r'''
#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE)
/* Native PC GPU joint observer: every output is exclusive, owner-private
 * and no-follow. Hold the JSONL fd for the entire one-shot session so an
 * on-disk journal name cannot redirect later events to a replacement inode. */
#include <fcntl.h>
#include <unistd.h>
static FILE *vh_map02_joint_log;
static unsigned vh_map02_joint_events_completed;
static FILE *VH_Map02SecureFile(const char *path)
{
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    FILE *output;
    if (fd == -1)
        return NULL;
    output = fdopen(fd, "wb");
    if (!output)
        close(fd);
    return output;
}
static FILE *VH_Map02SecureLog(const char *path)
{
    if (!vh_map02_joint_log)
        vh_map02_joint_log = VH_Map02SecureFile(path);
    return vh_map02_joint_log;
}
static int VH_Map02FlushLog(FILE *log)
{
    if (!log || ferror(log) || fflush(log) != 0 || ferror(log))
        return -1;
    return 0;
}
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
    for anchor in (FRAME_FUNCTION, ORIGINAL_GPU_MARKER, RELEASE,
                   EVENT_ANCHOR, *PRIVATE_FILE_OPENERS):
        if combined.count(anchor) != 1:
            raise ValueError("joint MAP02 private GPU hook anchor changed")
    combined = combined.replace(
        FRAME_FUNCTION, "static int VH_Map02JointGpuSessionReady(void);\n" +
        FRAME_FUNCTION, 1)
    combined = combined.replace(
        RELEASE,
        "    if (!VH_Map02JointGpuSessionReady())\n"
        "        _exit(96);\n" + RELEASE, 1)
    # Only the joint instrumentation gets exclusive 0600/O_NOFOLLOW
    # publication; normal PC GPU and the independent opt-in probe are
    # unchanged. Preserve GPU_CAPTURE-only builds with preprocessor arms.
    combined = combined.replace(EVENT_ANCHOR,
                                SECURE_JOURNAL + "\n" + EVENT_ANCHOR, 1)
    file_names = ("snapshot_path", "upload_path")
    for i, name in enumerate(file_names):
        source_line = PRIVATE_FILE_OPENERS[i]
        replacement_line = (
            "#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE)\n"
            + source_line.split("file =", 1)[0]
            + "file = VH_Map02SecureFile(" + name + ");\n"
            + "#else\n" + source_line + "\n#endif"
        )
        combined = combined.replace(source_line, replacement_line, 1)
    combined = combined.replace(
        PRIVATE_FILE_OPENERS[2],
        "#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE)\n"
        "    log = VH_Map02SecureLog(log_path);\n"
        "#else\n" + PRIVATE_FILE_OPENERS[2] + "\n#endif", 1)
    combined = combined.replace(
        PRIVATE_FILE_OPENERS[3],
        "#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE)\n"
        "    if (VH_Map02FlushLog(log) == 0)\n"
        "        ++vh_map02_joint_events_completed;\n"
        "#else\n" + PRIVATE_FILE_OPENERS[3] + "\n#endif", 1)
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
