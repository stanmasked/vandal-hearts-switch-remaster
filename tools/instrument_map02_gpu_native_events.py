#!/usr/bin/env python3
"""Create an opt-in read-only patch of the exact pinned PC libgpu.c.

Runtime capture works ONLY after the user explicitly sets both
VH_MAP02_GPU_CAPTURE_DIR (an existing private directory) and
VH_MAP02_GPU_CAPTURE_FRAME (positive DrawOTag frame number). It records
bounded BEFORE/AFTER native BGR555 VRAM snapshots for actual GPU transfer
calls and for *each* walked DrawOTag primitive (including SPRT, TILE,
DR_MODE). This is command-order evidence, NOT a source-keyed MAP02 trace,
not a PS1 GPU command trace, and not a substitute for authenticated
original game assets. It never alters the normal compiled GPU backend.
"""
import argparse
import json
from pathlib import Path

from tools.prepare_map02_pcport import git_blob_sha1

PINNED_SOURCE = "9d0fab71c45ed09dda072cfeacd557ab9c5d81e5"
GUARD = "VH_MAP02_GPU_CAPTURE"
ANCHORS = {
    "helpers": '#define VRAM_H 512\n',
    "load_before": '    if (rect->w > 0 && rect->h > 0) TrcWrite(\'L\', rect, 8, src, (u32)(rect->w * rect->h * 2));',
    "load_after": '    HiresMirrorRect(rect->x, rect->y, rect->w, rect->h);   /* keep the hi-res FB in sync (backgrounds) */',
    "move_before": '    { int xy[2]; xy[0] = x; xy[1] = y; TrcWrite(\'M\', rect, 8, xy, 8); }',
    "move_after": '    HiresMirrorRect(x, y, rect->w, rect->h);   /* keep the hi-res FB in sync (VRAM->VRAM blit) */',
    "clear_before": '    { unsigned char rgb[3]; rgb[0] = r; rgb[1] = g; rgb[2] = b; TrcWrite(\'C\', rect, 8, rgb, 3); }',
    "clear_after": '    FillRectRaw(rect->x, rect->y, rect->w, rect->h, r, g, b);',
    "draw_before": '            switch (type) {',
    "draw_after": '            default:\n                break;\n            }\n        }\n        nextTok = rawTagOfCur;',
}
HELPERS = r'''
#if defined(VH_MAP02_GPU_CAPTURE)
/* The recorder is deliberately capped; it captures only when BOTH local
 * environment variables are explicit. It is single-threaded: DrawOTag's
 * native pass is synchronous and the deferred HD worker pass isn't traced.
 * No output files are written by baseline (non-opt-in) builds. */
#define VH_CAPTURE_LIMIT 64u
static unsigned vh_capture_seq;
static const char *vh_capture_dir;
static unsigned long vh_capture_frame;
static int vh_capture_init;
static void VH_CaptureInit(void) {
    const char *value;
    char *end = NULL;
    if (vh_capture_init) return;
    vh_capture_init = 1;
    vh_capture_dir = getenv("VH_MAP02_GPU_CAPTURE_DIR");
    value = getenv("VH_MAP02_GPU_CAPTURE_FRAME");
    if (!vh_capture_dir || !vh_capture_dir[0] || !value || !value[0]) {
        vh_capture_frame = 0;
        return;
    }
    vh_capture_frame = strtoul(value, &end, 10);
    if (end == value || !end || *end != '\0' ||
        vh_capture_frame == 0 || vh_capture_frame > 0xffffffffUL)
        vh_capture_frame = 0;
}
static void VH_CaptureEvent(const char *phase, const char *operation, int transfer,
                            const RECT *rect, const unsigned short *upload,
                            size_t upload_words, int dest_x, int dest_y,
                            int r, int g, int b, int type, int semi,
                            const POLY_FT4 *quad) {
    char snapshot_path[1024], upload_path[1024], log_path[1024];
    char snapshot_name[64], upload_name[64];
    const void *vram;
    size_t bytes = 0;
    FILE *file, *log;
    int n;
    unsigned seq;
    VH_CaptureInit();
    if (!vh_capture_frame || vh_capture_seq >= VH_CAPTURE_LIMIT ||
        (transfer ? (unsigned long)s_drawFrame + 1ul != vh_capture_frame
                  : (unsigned long)s_drawFrame != vh_capture_frame))
        return;
    seq = vh_capture_seq++;
    n = snprintf(snapshot_name, sizeof snapshot_name, "gpu-%04u-vram.bin", seq);
    if (n < 0 || (size_t)n >= sizeof snapshot_name) return;
    n = snprintf(snapshot_path, sizeof snapshot_path, "%s/%s",
                 vh_capture_dir, snapshot_name);
    if (n < 0 || (size_t)n >= sizeof snapshot_path) return;
    vram = PC_GpuVramBytes(&bytes);
    if (!vram || bytes != 1024u * 512u * 2u) return;
    file = fopen(snapshot_path, "wb");
    if (!file) return;
    if (fwrite(vram, 1u, bytes, file) != bytes || fclose(file) != 0) return;
    upload_name[0] = '\0';
    if (upload && upload_words > 0u && upload_words <= 16384u) {
        n = snprintf(upload_name, sizeof upload_name, "gpu-%04u-upload.bin", seq);
        if (n < 0 || (size_t)n >= sizeof upload_name) return;
        n = snprintf(upload_path, sizeof upload_path, "%s/%s",
                     vh_capture_dir, upload_name);
        if (n < 0 || (size_t)n >= sizeof upload_path) return;
        file = fopen(upload_path, "wb");
        if (!file) return;
        /* Original PC binary layout is little-endian on supported hosts. */
        if (fwrite(upload, sizeof(unsigned short), upload_words, file) != upload_words ||
            fclose(file) != 0) return;
    }
    n = snprintf(log_path, sizeof log_path, "%s/gpu-native-events.jsonl", vh_capture_dir);
    if (n < 0 || (size_t)n >= sizeof log_path) return;
    log = fopen(log_path, "ab");
    if (!log) return;
    fprintf(log, "{\"stage\":\"native_vram\",\"step\":%u,\"frame\":%u,"
            "\"phase\":\"%s\",\"operation\":\"%s\",\"snapshot\":\"%s\","
            "\"rect\":", seq, s_drawFrame, phase, operation, snapshot_name);
    if (rect)
        fprintf(log, "[%d,%d,%d,%d]", rect->x, rect->y, rect->w, rect->h);
    else
        fputs("null", log);
    fprintf(log, ",\"dest\":[%d,%d],\"rgb\":[%d,%d,%d],"
            "\"primitive_type\":%d,\"semi\":%d,"
            "\"window\":[%d,%d,%d,%d],\"draw_mode\":[%d,%d,%d],"
            "\"upload\":\"%s\",\"ft4\":",
            dest_x, dest_y, r, g, b, type, semi,
            s_twMaskX, s_twMaskY, s_twOffX, s_twOffY,
            s_drawModeTPage, s_drawModeAbr, s_drawModeDither,
            upload_name);
    if (quad)
        fprintf(log, "{\"tpage\":%u,\"clut\":%u,"
                "\"xy\":[%d,%d,%d,%d,%d,%d,%d,%d],"
                "\"uv\":[%u,%u,%u,%u,%u,%u,%u,%u]}",
                (unsigned)quad->tpage, (unsigned)quad->clut,
                quad->x0,quad->y0,quad->x1,quad->y1,
                quad->x2,quad->y2,quad->x3,quad->y3,
                quad->u0,quad->v0,quad->u1,quad->v1,
                quad->u2,quad->v2,quad->u3,quad->v3);
    else
        fputs("null", log);
    fputs("}\n", log);
    fclose(log);
}
#endif
'''

def replace_one(source, anchor, replacement, label):
    count = source.count(anchor)
    if count != 1:
        raise ValueError(f"{label}: expected one pinned source anchor, got {count}")
    return source.replace(anchor, replacement, 1)

def instrument(source):
    if GUARD in source:
        raise ValueError("already instrumented")
    # The helpers use static GPU state; insert after globals, before GetTPage.
    marker='/* ---- GetTPage / GetClut (psx-spx "Texpage Attribute" / "Clut Attribute") */'
    source = replace_one(source, marker, HELPERS + "\n" + marker, "capture helpers")
    def wrap(block, hook):
        return "#if defined(VH_MAP02_GPU_CAPTURE)\n" + hook + "\n#endif\n" + block
    source=replace_one(source,ANCHORS["load_before"],
         wrap(ANCHORS["load_before"],
              '    VH_CaptureEvent("before","load",1,rect,NULL,0u,0,0,0,0,0,0,0,NULL);'),
         "pre-LoadImage")
    source=replace_one(source,ANCHORS["load_after"],
         ANCHORS["load_after"]+'\n#if defined(VH_MAP02_GPU_CAPTURE)\n'
         '    VH_CaptureEvent("after","load",1,rect,src,\n'
         '       rect->w > 0 && rect->h > 0 && rect->w <= 128 && rect->h <= 128 ?\n'
         '       (size_t)rect->w*(size_t)rect->h : 0u,0,0,0,0,0,0,0,NULL);\n#endif',
         "post-LoadImage")
    source=replace_one(source,ANCHORS["move_before"],
         wrap(ANCHORS["move_before"],
              '    VH_CaptureEvent("before","move",1,rect,NULL,0u,x,y,0,0,0,0,0,NULL);'),
         "pre-MoveImage")
    source=replace_one(source,ANCHORS["move_after"],
         ANCHORS["move_after"]+'\n#if defined(VH_MAP02_GPU_CAPTURE)\n'
         '    VH_CaptureEvent("after","move",1,rect,NULL,0u,x,y,0,0,0,0,0,NULL);\n#endif',
         "post-MoveImage")
    source=replace_one(source,ANCHORS["clear_before"],
         wrap(ANCHORS["clear_before"],
              '    VH_CaptureEvent("before","clear",1,rect,NULL,0u,0,0,r,g,b,0,0,NULL);'),
         "pre-ClearImage")
    source=replace_one(source,ANCHORS["clear_after"],
         ANCHORS["clear_after"]+'\n#if defined(VH_MAP02_GPU_CAPTURE)\n'
         '    VH_CaptureEvent("after","clear",1,rect,NULL,0u,0,0,r,g,b,0,0,NULL);\n#endif',
         "post-ClearImage")
    source=replace_one(source,ANCHORS["draw_before"],
         '#if defined(VH_MAP02_GPU_CAPTURE)\n'
         '            VH_CaptureEvent("before","draw",0,NULL,NULL,0u,0,0,0,0,0,'
         'type,semi,type == PC_GPU_PRIM_POLY_FT4 ? (POLY_FT4 *)cur : NULL);\n'
         '#endif\n'+ANCHORS["draw_before"],
         "DrawOTag before primitive")
    source=replace_one(source,ANCHORS["draw_after"],
         '            default:\n                break;\n            }\n'
         '#if defined(VH_MAP02_GPU_CAPTURE)\n'
         '            VH_CaptureEvent("after","draw",0,NULL,NULL,0u,0,0,0,0,0,'
         'type,semi,type == PC_GPU_PRIM_POLY_FT4 ? (POLY_FT4 *)cur : NULL);\n'
         '#endif\n        }\n        nextTok = rawTagOfCur;',
         "DrawOTag after primitive")
    return source

def prepare(source_path, destination):
    if destination.exists():
        raise ValueError("output already exists; refusing overwrite")
    raw=source_path.read_bytes()
    if git_blob_sha1(raw) != PINNED_SOURCE:
        raise ValueError("original libgpu.c Git blob SHA differs from pinned PC port")
    modified=instrument(raw.decode("utf-8"))
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(modified,encoding="utf-8")
    return {
        "source_pinned":True,"enabled_by":"-DVH_MAP02_GPU_CAPTURE",
        "environment":["VH_MAP02_GPU_CAPTURE_DIR","VH_MAP02_GPU_CAPTURE_FRAME"],
        "transfer_hooks":["LoadImage","MoveImage","ClearImage"],
        "walk_hooks":["DrawOTag primitive before","DrawOTag primitive after"],
        "max_snapshot_records":64,
        "original_gameplay_captured":False,
        "original_content_published":False,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_libgpu",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        result=prepare(args.original_libgpu,args.output)
    except (ValueError,OSError,UnicodeError) as error:
        p.error(str(error))
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__=="__main__":
    main()
