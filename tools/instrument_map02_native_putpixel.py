#!/usr/bin/env python3
"""Generate a *separate* opt-in original PC PutPixel BGR555 write observer.

Do not alter the actual WritePixel/BlendG1 decision. Observe one selected
native VRAM address after it has passed raster clipping and any texel skip.
The emitter logs before/input/after, ABR, semi, textured and accurate mode.
Missing events do NOT prove texture-zero, clipping, transparency or masking.
The selected private PC-port source is pinned by its literal Git blob SHA1.
"""
import argparse
import json
from pathlib import Path
from tools.prepare_map02_pcport import git_blob_sha1

BLOB = "ba8a05d161ad778c0b75e452ff0a11ed163c65cd"
FLAG = "VH_MAP02_PUTPIXEL_SAMPLE"
INSERT_AFTER = "static unsigned short s_vram[VRAM_H][VRAM_W];"
CALL = "    WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);"

HELPERS = r'''
#if defined(VH_MAP02_PUTPIXEL_SAMPLE)
/* Read-only, bounded, single coordinate diagnostic. Not thread-safe:
 * only native target==0 in the synchronous PC GPU pass is observed.
 * Both location and destination are explicit private opt-in inputs.
 * No log I/O occurs for the normal binary without this macro. */
#define VH_PIXEL_SAMPLE_MAX 64u
static int AccurateEnabled(void); /* defined by the original rasterizer */
static int vh_pixel_sample_init;
static int vh_pixel_sample_active;
static int vh_pixel_sample_x, vh_pixel_sample_y;
static unsigned vh_pixel_sample_count;
static const char *vh_pixel_sample_dir;
static void VH_PixelSampleInit(void) {
    const char *vx, *vy;
    char *endx = NULL, *endy = NULL;
    long x, y;
    if (vh_pixel_sample_init) return;
    vh_pixel_sample_init = 1;
    vh_pixel_sample_dir = getenv("VH_MAP02_PUTPIXEL_DIR");
    vx = getenv("VH_MAP02_PUTPIXEL_X");
    vy = getenv("VH_MAP02_PUTPIXEL_Y");
    if (!vh_pixel_sample_dir || vh_pixel_sample_dir[0] != '/' ||
        !vx || !*vx || !vy || !*vy) return;
    x = strtol(vx, &endx, 10);
    y = strtol(vy, &endy, 10);
    if (endx == vx || !endx || *endx != '\0' ||
        endy == vy || !endy || *endy != '\0' ||
        x < 0 || x >= VRAM_W || y < 0 || y >= VRAM_H) return;
    vh_pixel_sample_x = (int)x;
    vh_pixel_sample_y = (int)y;
    vh_pixel_sample_active = 1;
}
static int VH_PixelSampleSelected(int x, int y) {
    VH_PixelSampleInit();
    return vh_pixel_sample_active &&
           vh_pixel_sample_count < VH_PIXEL_SAMPLE_MAX &&
           x == vh_pixel_sample_x && y == vh_pixel_sample_y;
}
static void VH_PixelSampleRecord(int x, int y, unsigned short before,
                                 unsigned short front, unsigned short after,
                                 int abr, int semi, int textured) {
    char path[1024];
    int size;
    FILE *file;
    size = snprintf(path, sizeof path, "%s/putpixel-native-events.jsonl",
                    vh_pixel_sample_dir);
    if (size < 0 || (size_t)size >= sizeof path) return;
    file = fopen(path, "ab");
    if (!file) return;
    if (fprintf(file,
        "{\"stage\":\"native_putpixel\",\"step\":%u,"
        "\"x\":%d,\"y\":%d,\"before\":%u,\"front\":%u,"
        "\"after\":%u,\"abr\":%d,\"semi\":%d,"
        "\"textured\":%d,\"accurate\":%d}\n",
        vh_pixel_sample_count, x, y, (unsigned)before, (unsigned)front,
        (unsigned)after, abr, semi, textured, AccurateEnabled()) < 0) {
        fclose(file);
        return;
    }
    if (fclose(file) != 0) return;
    vh_pixel_sample_count++;
}
#endif
'''


def replace_once(source, needle, replacement):
    count = source.count(needle)
    if count != 1:
        raise ValueError(f"pinned PutPixel source changed: expected one anchor, got {count}")
    return source.replace(needle, replacement, 1)


def instrument(source):
    if FLAG in source:
        raise ValueError("sample observer already installed")
    source = replace_once(source, INSERT_AFTER, INSERT_AFTER + "\n" + HELPERS)
    # Callbacks are inserted only on native target=0; the hires pass has
    # a separate early return in PutPixel and is unaffected.
    replacement = r'''#if defined(VH_MAP02_PUTPIXEL_SAMPLE)
    {
        int vh_sample = VH_PixelSampleSelected(x, y);
        unsigned short vh_before = vh_sample ? s_vram[y][x] : 0;
#endif
    WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);
#if defined(VH_MAP02_PUTPIXEL_SAMPLE)
        if (vh_sample) VH_PixelSampleRecord(x, y, vh_before, c, s_vram[y][x],
                                           abr, semiTrans, textured);
    }
#endif'''
    source = replace_once(source, CALL, replacement)
    return source


def prepare(original_path, destination):
    if destination.exists():
        raise ValueError("destination exists; refusing to overwrite")
    raw = original_path.read_bytes()
    if git_blob_sha1(raw) != BLOB:
        raise ValueError("original PC raster Git blob is not the pinned source")
    patched = instrument(raw.decode("utf-8"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(patched, encoding="utf-8")
    return {
        "source_pinned": True,
        "enabled_by": "-DVH_MAP02_PUTPIXEL_SAMPLE",
        "requires_environment": [
            "VH_MAP02_PUTPIXEL_DIR", "VH_MAP02_PUTPIXEL_X",
            "VH_MAP02_PUTPIXEL_Y",
        ],
        "max_pixel_records": 64,
        "native_vram_only": True,
        "actual_gameplay_captured": False,
        "pixel_reason_inferred_from_missing_event": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_raster", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    try:
        result = prepare(a.original_raster, a.output)
    except (OSError, ValueError, UnicodeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
