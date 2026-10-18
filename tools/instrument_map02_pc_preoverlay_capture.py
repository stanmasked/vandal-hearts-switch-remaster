#!/usr/bin/env python3
"""Source-pinned opt-in PC scratch tap immediately BEFORE overlay compositing.

No original binary, CD sectors, saved image or private RGB24 bytes are
accessed here. The resulting generated source is private build input.
"""
from pathlib import Path
import argparse

from tools.prepare_map02_pcport import git_blob_sha1
from tools.check_map02_pc_present_rgb24_source import BLOB_SHA1, ANCHORS

SOURCE = "platform/pc/src/pc_gpu_window.c"
ANCHOR = "    /* Langpack movie subtitles:"
DEFINE = "VH_MAP02_PC_PREOVERLAY_CAPTURE"


def instrument(source):
    if git_blob_sha1(source.encode("utf-8")) != BLOB_SHA1:
        raise ValueError("pinned PC SDL present C source blob differs")
    if any(source.count(a) != 1 for a in ANCHORS):
        raise ValueError("PC pre-overlay original conversion anchors drifted")
    if source.count(ANCHOR) != 1:
        raise ValueError("PC pre-overlay capture anchor missing or ambiguous")
    setup = (
        "#ifdef " + DEFINE + "\n"
        "#include \"map02_pc_preoverlay_capture.h\"\n"
        "extern unsigned s_drawFrame;\n"
        "extern int HiresActive(void);\n"
        "#endif\n"
    )
    callback = (
        "#ifdef " + DEFINE + "\n"
        "    /* Exactly AFTER BGR555->RGB24, BEFORE subtitles, OSD and menu. */\n"
        "    if (!vh_map02_pc_capture_preoverlay(s_drawFrame, s_rgbaScratch,\n"
        "            (unsigned)w, (unsigned)h,\n"
        "            (s_movieOverlay || s_movieOverlayRGB) ? 1 : 0,\n"
        "            HiresActive())) {\n"
        "        fputs(\"MAP02 private PC RGB24 capture failed closed\\n\", stderr);\n"
        "        abort();\n"
        "    }\n"
        "#endif\n"
    )
    result = setup + source.replace(ANCHOR, callback + ANCHOR, 1)
    if (result.index("unsigned char *out = &s_rgbaScratch") >=
            result.index("vh_map02_pc_capture_preoverlay(s_drawFrame") or
            result.index("vh_map02_pc_capture_preoverlay(s_drawFrame") >=
            result.index("/* Langpack movie subtitles:")):
        raise ValueError("PC pre-overlay capture hook ordering invalid")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pc_checkout", type=Path)
    p.add_argument("new_generated_output_file", type=Path)
    args = p.parse_args()
    input_path = args.pinned_pc_checkout / SOURCE
    output = args.new_generated_output_file
    if output.exists() or output.is_symlink():
        p.error("PC capture output must be new and non-symlinked")
    if (not output.parent.is_dir() or output.parent.is_symlink() or
            (output.parent.stat().st_mode & 0o077)):
        p.error("PC capture output requires existing owner-private directory")
    try:
        generated = instrument(input_path.read_text(encoding="utf-8"))
        with output.open("x", encoding="utf-8") as f:
            f.write(generated)
        output.chmod(0o600)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    print("Generated private source-pinned RGB24 capture hook. No game data read.")


if __name__ == "__main__":
    main()
