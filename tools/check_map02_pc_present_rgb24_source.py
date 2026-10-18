#!/usr/bin/env python3
"""Fail closed if pinned PC GPU RGB conversion or overlay boundary drifts."""
import argparse
import json
from pathlib import Path

from tools.prepare_map02_pcport import git_blob_sha1

BLOB_SHA1 = "47bc26af6134e70d7f307a560ef1a4a5a287aab3"
RELATIVE = "platform/pc/src/pc_gpu_window.c"

# Check the precise source algorithm that verify_map02_pc_present_rgb24
# independently reproduces. A hash check alone is not a semantic check.
ANCHORS = (
    "void PC_GpuPresent(unsigned short *vram, int vramW, int vramH,",
    "if ((s_movieOverlay || s_movieOverlayRGB) && s_movieOvW > 0",
    "int mshift = (s_movieOverlay != NULL && msubs == 4) ? 2 : 0;",
    "for (py = 0; py < h; py++) {",
    "for (px = 0; px < w; px++) {",
    "unsigned short c = vram[(y + (py >> mshift)) * vramW + (x + (px >> mshift))];",
    "unsigned char *out = &s_rgbaScratch[((h - 1 - py) * w + px) * 3];",
    "int r5 = c & 0x1F, g5 = (c >> 5) & 0x1F, b5 = (c >> 10) & 0x1F;",
    "out[0] = (unsigned char)((r5 << 3) | (r5 >> 2));",
    "out[1] = (unsigned char)((g5 << 3) | (g5 >> 2));",
    "out[2] = (unsigned char)((b5 << 3) | (b5 >> 2));",
    "/* Langpack movie subtitles:",
    "if (s_osdEnabled && g_camOsdText[0]) osdDrawText",
    "if (PC_OverlayIsOpen()) PC_GpuDrawOverlay(w, h);",
)


def check_source(path):
    raw = Path(path).read_bytes()
    if git_blob_sha1(raw) != BLOB_SHA1:
        raise ValueError("original PC present conversion source blob has drifted")
    text = raw.decode("utf-8")
    positions = []
    for anchor in ANCHORS:
        if text.count(anchor) != 1:
            raise ValueError("pinned PC present source missing/duplicated RGB boundary")
        positions.append(text.index(anchor))
    if positions != sorted(positions):
        raise ValueError("PC present conversion and post-RGB overlay order changed")
    return {
        "original_source_blob_git_sha1": BLOB_SHA1,
        "verified_bgr555_to_bottom_up_rgb24_before_overlays": True,
        "movie_overlay_must_be_inactive_for_native_vram_match": True,
        "original_map02_frame_authenticated": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pc_checkout", type=Path)
    args = p.parse_args()
    try:
        result = check_source(args.pinned_pc_checkout / RELATIVE)
    except (OSError, UnicodeError, ValueError) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
