#!/usr/bin/env python3
"""Create an opt-in read-only patch of the exact pinned PC libgpu.c.

Runtime capture works ONLY after the user explicitly sets both
VH_MAP02_GPU_CAPTURE_DIR (an existing private directory) and
VH_MAP02_GPU_CAPTURE_FRAME (positive DrawOTag frame number). It records
bounded BEFORE/AFTER native BGR555 VRAM snapshots for actual GPU transfer
calls and for each DRAW primitive (F4, FT4, SPRT, TILE) walked by
DrawOTag plus state-only DR_MODE packets for exact GPU-state continuity.
This is command-order evidence, NOT a source-keyed MAP02 trace,
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
    "frame_end": "    TrcFrameEnd();",
}
HELPERS = r'''
#if defined(VH_MAP02_GPU_CAPTURE)
#if defined(VH_MAP02_POSIX_CAPTURE_WINDOWS)
#include <sys/stat.h>
#include <unistd.h>
#endif
#if defined(VH_MAP02_CAPTURE_SESSION)
#if !defined(VH_MAP02_POSIX_CAPTURE_WINDOWS)
#error "MAP02 capture sessions require bounded GPU windows"
#endif
#include "map02_capture_session.h"
#endif
/* The recorder is deliberately capped; it captures only when BOTH local
 * environment variables are explicit. It is single-threaded: DrawOTag's
 * native pass is synchronous and the deferred HD worker pass isn't traced.
 * No output files are written by baseline (non-opt-in) builds. */
#define VH_CAPTURE_LIMIT 64u
/* Receipt counters are self-reported, not proof of genuine retail gameplay. */
static unsigned vh_capture_seq, vh_capture_saved;
static unsigned long vh_capture_seen, vh_capture_before, vh_capture_after;
static unsigned long vh_capture_draw_before, vh_capture_transfer_before;
static int vh_capture_receipt_written;
static const char *vh_capture_dir;
static unsigned long vh_capture_frame;
static int vh_capture_init;
#if defined(VH_MAP02_POSIX_CAPTURE_WINDOWS)
static unsigned vh_capture_windows;
static int vh_capture_window_failed;
static int VH_CapturePrivateRoot(void) {
    struct stat st;
    return vh_capture_dir && lstat(vh_capture_dir, &st) == 0 &&
           S_ISDIR(st.st_mode) && (st.st_mode & 0777) == 0700 &&
           st.st_uid == geteuid();
}
#endif
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
#if defined(VH_MAP02_POSIX_CAPTURE_WINDOWS)
    value = getenv("VH_MAP02_GPU_CAPTURE_WINDOW_COUNT");
    if (value && *value) {
        if (strcmp(value, "2") != 0 || !VH_CapturePrivateRoot()) {
            vh_capture_frame = 0;
            return;
        }
        vh_capture_windows = 2u;
    }
#endif
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
    unsigned seq, local_seq, max_events = VH_CAPTURE_LIMIT;
    const char *directory;
#if defined(VH_MAP02_POSIX_CAPTURE_WINDOWS)
    char window_dir[1024];
    unsigned window_number;
#endif
    VH_CaptureInit();
    directory = vh_capture_dir;
    if (!vh_capture_frame ||
        (transfer ? (unsigned long)s_drawFrame + 1ul != vh_capture_frame
                  : (unsigned long)s_drawFrame != vh_capture_frame))
        return;
    if (vh_capture_seen < 0xffffffffUL) ++vh_capture_seen;
    if (strcmp(phase, "before") == 0) {
        if (vh_capture_before < 0xffffffffUL) ++vh_capture_before;
        if (transfer) {
            if (vh_capture_transfer_before < 0xffffffffUL)
                ++vh_capture_transfer_before;
        } else if (vh_capture_draw_before < 0xffffffffUL) {
            ++vh_capture_draw_before;
        }
    } else if (vh_capture_after < 0xffffffffUL) {
        ++vh_capture_after;
    }
#if defined(VH_MAP02_POSIX_CAPTURE_WINDOWS)
    if (vh_capture_windows) max_events = 2u * VH_CAPTURE_LIMIT;
#endif
    if (vh_capture_seq >= max_events) return;
    seq = vh_capture_seq++;
    local_seq = seq;
#if defined(VH_MAP02_POSIX_CAPTURE_WINDOWS)
    if (vh_capture_windows) {
        window_number = seq / VH_CAPTURE_LIMIT;
        local_seq = seq % VH_CAPTURE_LIMIT;
        n = snprintf(window_dir, sizeof window_dir, "%s/window-%03u",
                     vh_capture_dir, window_number);
        if (n <= 0 || (size_t)n >= sizeof window_dir) {
            vh_capture_window_failed = 1;
            return;
        }
        if (local_seq == 0 && mkdir(window_dir, 0700) != 0) {
            vh_capture_window_failed = 1;
            return;
        }
        directory = window_dir;
    }
#endif
    n = snprintf(snapshot_name, sizeof snapshot_name, "gpu-%04u-vram.bin", local_seq);
    if (n < 0 || (size_t)n >= sizeof snapshot_name) return;
    n = snprintf(snapshot_path, sizeof snapshot_path, "%s/%s",
                 directory, snapshot_name);
    if (n < 0 || (size_t)n >= sizeof snapshot_path) return;
    vram = PC_GpuVramBytes(&bytes);
    if (!vram || bytes != 1024u * 512u * 2u) return;
    file = fopen(snapshot_path, "wb");
    if (!file) return;
    {
        size_t produced = fwrite(vram, 1u, bytes, file);
        int closed = fclose(file);
        if (produced != bytes || closed != 0) return;
    }
    upload_name[0] = '\0';
    if (upload && upload_words > 0u && upload_words <= 16384u) {
        /* Match snapshot, JSONL step and all per-window upload filenames. */
        n = snprintf(upload_name, sizeof upload_name,
                     "gpu-%04u-upload.bin", local_seq);
        if (n < 0 || (size_t)n >= sizeof upload_name) return;
        n = snprintf(upload_path, sizeof upload_path, "%s/%s",
                     directory, upload_name);
        if (n < 0 || (size_t)n >= sizeof upload_path) return;
        file = fopen(upload_path, "wb");
        if (!file) return;
        /* Original PC binary layout is little-endian on supported hosts. */
        {
            size_t produced = fwrite(upload, sizeof(unsigned short), upload_words, file);
            int closed = fclose(file);
            if (produced != upload_words || closed != 0) return;
        }
    }
    n = snprintf(log_path, sizeof log_path, "%s/gpu-native-events.jsonl", directory);
    if (n < 0 || (size_t)n >= sizeof log_path) return;
    log = fopen(log_path, "ab");
    if (!log) return;
    fprintf(log, "{\"stage\":\"native_vram\",\"step\":%u,\"frame\":%u,"
            "\"phase\":\"%s\",\"operation\":\"%s\",\"snapshot\":\"%s\","
            "\"rect\":", local_seq, s_drawFrame, phase, operation, snapshot_name);
    if (rect)
        fprintf(log, "[%d,%d,%d,%d]", rect->x, rect->y, rect->w, rect->h);
    else
        fputs("null", log);
    fprintf(log, ",\"dest\":[%d,%d],\"rgb\":[%d,%d,%d],"
            "\"primitive_type\":%d,\"semi\":%d,"
            "\"window\":[%d,%d,%d,%d],\"draw_env\":[%d,%d,%d,%d,%d,%d],\"draw_mode\":[%d,%d,%d],"
            "\"upload\":\"%s\",\"ft4\":",
            dest_x, dest_y, r, g, b, type, semi,
            s_twMaskX, s_twMaskY, s_twOffX, s_twOffY,
            s_drawEnv.clip.x, s_drawEnv.clip.y,
            s_drawEnv.clip.w, s_drawEnv.clip.h,
            s_drawEnv.ofs[0], s_drawEnv.ofs[1],
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
    if (ferror(log) == 0) {
        if (fclose(log) == 0) ++vh_capture_saved;
    } else {
        (void)fclose(log);
    }
}
/* Exclusive completion receipt; never overwrites existing status files.
 * It detects source-hook loss, NOT provenance or full game frame coverage. */
static void VH_CaptureFinish(unsigned frame, int walk_finished) {
    char status_path[1024];
    FILE *file;
    int n, balanced;
    VH_CaptureInit();
    if (!vh_capture_frame || (unsigned long)frame != vh_capture_frame ||
        vh_capture_receipt_written) return;
    vh_capture_receipt_written = 1;
#if defined(VH_MAP02_POSIX_CAPTURE_WINDOWS)
    if (vh_capture_windows) {
        char session_field[80] = "";
        unsigned expected_windows = (vh_capture_saved + VH_CAPTURE_LIMIT - 1u)
                                    / VH_CAPTURE_LIMIT;
#if defined(VH_MAP02_CAPTURE_SESSION)
        {
            const char *token = vh_map02_capture_session_token();
            if (!token || snprintf(session_field, sizeof session_field,
                      ",\"capture_session\":\"%s\"", token) <= 0)
                return;
        }
#endif
        unsigned maximum = 2u * VH_CAPTURE_LIMIT;
        n = snprintf(status_path, sizeof status_path, "%s/gpu-native-window-index.json",
                     vh_capture_dir);
        if (n <= 0 || (size_t)n >= sizeof status_path) return;
        file = fopen(status_path, "wx");
        if (!file) return;
        balanced = vh_capture_before == vh_capture_after &&
                   vh_capture_seen == vh_capture_before + vh_capture_after;
        fprintf(file,
          "{\"schema\":\"vh.map02.native-windows.v1\","
          "\"gpu_draw_frame\":%u,\"window_capacity_events\":64,"
          "\"configured_windows\":2,\"windows_written\":%u,"
          "\"observed_hooks\":%lu,\"before_hooks\":%lu,"
          "\"after_hooks\":%lu,\"draw_before_hooks\":%lu,"
          "\"transfer_before_hooks\":%lu,\"indexed_hooks\":%u,"
          "\"written_hooks\":%u,\"limit_reached\":%s,"
          "\"walk_finished\":%s,\"hooks_balanced\":%s,"
          "\"write_failed\":%s,"
          "\"recorded_window_closed_without_detected_loss\":%s%s}\n",
          frame, expected_windows,
          vh_capture_seen, vh_capture_before, vh_capture_after,
          vh_capture_draw_before, vh_capture_transfer_before,
          vh_capture_seq, vh_capture_saved,
          vh_capture_seq >= maximum ? "true" : "false",
          walk_finished ? "true" : "false",
          balanced ? "true" : "false",
          vh_capture_window_failed ? "true" : "false",
          (walk_finished && balanced && !vh_capture_window_failed &&
           vh_capture_seen == vh_capture_seq &&
           vh_capture_saved == vh_capture_seq &&
           vh_capture_seq < maximum) ? "true" : "false",
           session_field);
        (void)fclose(file);
        return;
    }
#endif
    n = snprintf(status_path, sizeof status_path,
                 "%s/gpu-native-capture-status.json", vh_capture_dir);
    if (n < 0 || (size_t)n >= sizeof status_path) return;
    file = fopen(status_path, "wx");
    if (!file) return;
    balanced = vh_capture_before == vh_capture_after &&
               vh_capture_seen == vh_capture_before + vh_capture_after;
    fprintf(file,
      "{\"schema\":\"vh.map02.native-capture-status.v1\","
      "\"gpu_draw_frame\":%u,\"observed_hooks\":%lu,"
      "\"before_hooks\":%lu,\"after_hooks\":%lu,"
      "\"draw_before_hooks\":%lu,\"transfer_before_hooks\":%lu,"
      "\"indexed_hooks\":%u,\"written_hooks\":%u,"
      "\"limit_reached\":%s,\"walk_finished\":%s,"
      "\"hooks_balanced\":%s,"
      "\"observed_window_closed_without_detected_loss\":%s}\n",
      frame, vh_capture_seen, vh_capture_before, vh_capture_after,
      vh_capture_draw_before, vh_capture_transfer_before,
      vh_capture_seq, vh_capture_saved,
      vh_capture_seq >= VH_CAPTURE_LIMIT ? "true" : "false",
      walk_finished ? "true" : "false",
      balanced ? "true" : "false",
      (walk_finished && balanced && vh_capture_seen == vh_capture_seq &&
       vh_capture_saved == vh_capture_seq &&
       vh_capture_seq < VH_CAPTURE_LIMIT) ? "true" : "false");
    (void)fclose(file);
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
    # Capture state-only DR_MODE as well: PR #55 checks the exact
    # pre/post GPU state transition and requires contiguous VRAM across
    # adjacent DrawOTag events. DR_MODE cannot be omitted as a gap.
    draw_only = ('type == PC_GPU_PRIM_POLY_F4 || type == PC_GPU_PRIM_POLY_FT4 || '
                 'type == PC_GPU_PRIM_SPRT || type == PC_GPU_PRIM_TILE || '
                 'type == PC_GPU_PRIM_DR_MODE')
    source=replace_one(source,ANCHORS["draw_before"],
         '#if defined(VH_MAP02_GPU_CAPTURE)\n'
         '            if (' + draw_only + ')\n'
         '                VH_CaptureEvent("before","draw",0,NULL,NULL,0u,0,0,0,0,0,'
         'type,semi,type == PC_GPU_PRIM_POLY_FT4 ? (POLY_FT4 *)cur : NULL);\n'
         '#endif\n'+ANCHORS["draw_before"],
         "DrawOTag before primitive")
    source=replace_one(source,ANCHORS["draw_after"],
         '            default:\n                break;\n            }\n'
         '#if defined(VH_MAP02_GPU_CAPTURE)\n'
         '            if (' + draw_only + ')\n'
         '                VH_CaptureEvent("after","draw",0,NULL,NULL,0u,0,0,0,0,0,'
         'type,semi,type == PC_GPU_PRIM_POLY_FT4 ? (POLY_FT4 *)cur : NULL);\n'
         '#endif\n        }\n        nextTok = rawTagOfCur;',
         "DrawOTag after primitive")
    source=replace_one(source,ANCHORS["frame_end"],
         '#if defined(VH_MAP02_GPU_CAPTURE)\n'
         '    VH_CaptureFinish(s_drawFrame, nextTok == 0);\n'
         '#endif\n'+ANCHORS["frame_end"], "DrawOTag completion")
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
        "completion_receipt":"gpu-native-capture-status.json",
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
