#!/usr/bin/env python3
"""Differential test a full indexed4 tpage against the exact pinned PC SampleTexture.

Synthetic full VRAM. Extract real TPageOrigin/SampleTexture from the pinned
public PC-port pc_raster.c, compile both and compare every one of 256*256
texels on eight register scenarios. No proprietary data is needed or copied.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from tools.prepare_map02_pcport import git_blob_sha1

PINNED_RASTER_BLOB = "ba8a05d161ad778c0b75e452ff0a11ed163c65cd"
FUNCTIONS = (
    "void TPageOrigin(int tpage, int *x, int *y, int *tp) {",
    "static unsigned short SampleTexture(const RenderCtx *rc, int tpage, int clut, int u, int v) {",
)
ANCHORS = (
    "*x = (tpage & 0xF) * 64;",
    "*y = ((tpage >> 4) & 1) * 256;",
    "*tp = (tpage >> 7) & 3;",
    "int clutX = (clut & 0x3F) * 16;",
    "int clutY = (clut >> 6) & 0x1FF;",
    "u = (u & ~(rc->twMaskX * 8)) | ((rc->twOffX & rc->twMaskX) * 8);",
    "v = (v & ~(rc->twMaskY * 8)) | ((rc->twOffY & rc->twMaskY) * 8);",
    "unsigned short hw = s_vram[tpY + v][tpX + u / 4];",
    "int index = (hw >> ((u % 4) * 4)) & 0xF;",
    "raw = s_vram[clutY][clutX + index];",
)


def extract_sample_functions(source: str) -> str:
    segments = []
    for anchor in FUNCTIONS:
        if source.count(anchor) != 1:
            raise ValueError("pinned raster function boundary changed: " + anchor)
        i = source.index(anchor)
        j = source.find("\n}\n", i)
        if j < 0:
            raise ValueError("pinned raster function end changed: " + anchor)
        segments.append(source[i:j + 3])
    content = "\n".join(segments)
    for needle in ANCHORS:
        if needle not in content:
            raise ValueError("pinned GPU 4bpp source arithmetic changed: " + needle)
    return content


HARNESS = r"""
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "map02_vram4_page.h"
typedef struct {
    int twMaskX,twMaskY,twOffX,twOffY;
} RenderCtx;
static unsigned short s_vram[512][1024];
static uint8_t raw[VH_MAP02_VRAM_BYTES];
static uint8_t page[VH_MAP02_VRAM4_ATLAS_BYTES];
static uint8_t palette[VH_MAP02_VRAM4_CLUT_BYTES];

{SOURCE}

static uint16_t palette_word(unsigned ix) {
    return (uint16_t)((uint16_t)palette[ix*2] |
                       ((uint16_t)palette[ix*2+1]<<8));
}
static unsigned sample_at(unsigned u,unsigned v) {
    uint8_t b=page[(size_t)v*128u+u/2u];
    return (unsigned)((b>>((u&1u)*4u))&15u);
}
int main(void) {
    static const int cases[][6] = {
        {5,31978,0,0,0,0},
        {5,31978,1,1,0,0},
        {5,31978,1,1,1,1},
        {31,65535,31,31,0,0},
        {31,65535,31,31,31,31},
        {0,0,0,0,0,0},
        {16,1234,17,9,4,5},
        {7,0,31,0,3,0},
        /* Page X/Y bounds, including the final 4bpp page at x=960,y=256. */
        {0,0,0,0,0,0},
        {15,63,0,0,0,0},
        {16,32704,0,0,0,0},
        {31,32767,0,0,0,0},
        /* Valid CLUT extremes: first/last palette on rows 0 and 511. */
        {0,0,31,31,0,0},
        {31,65535,31,31,31,31},
        {15,63,31,0,31,0},
        {16,65472,0,31,0,31},
        /* Asymmetric GP0(E2h) masks, offsets and 8-texel boundaries. */
        {1,64,1,0,0,0},
        {2,128,0,1,0,0},
        {3,192,1,1,1,0},
        {4,256,3,3,1,2},
        {5,320,7,0,4,0},
        {6,384,0,7,0,4},
        {8,512,15,15,15,7},
        {9,576,16,16,0,16},
        {10,640,17,17,16,1},
        {11,704,30,29,30,29},
        {12,768,31,1,1,31},
        {13,832,1,31,31,1},
        {14,896,5,10,31,31},
        {17,960,10,5,31,31},
        {18,1024,24,3,24,3},
        {30,65088,31,30,0,31}
    };
    uint32_t state=UINT32_C(0x19371016);
    unsigned t,x,y;
    unsigned total=0;
    VhMap02Vram4PageStats stats;
    for(y=0;y<512u;++y)
        for(x=0;x<1024u;++x) {
            state=state*UINT32_C(1664525)+UINT32_C(1013904223);
            s_vram[y][x]=(unsigned short)(state>>16);
            raw[2u*((size_t)y*1024u+x)]=(uint8_t)s_vram[y][x];
            raw[2u*((size_t)y*1024u+x)+1]=(uint8_t)(s_vram[y][x]>>8);
        }
    for(t=0;t<sizeof cases/sizeof cases[0];++t) {
        const int *fixture=cases[t];
        RenderCtx rc={fixture[2],fixture[3],fixture[4],fixture[5]};
        VhMap02Vram4Registers regs={
            fixture[0],fixture[1],fixture[2],fixture[3],fixture[4],fixture[5]
        };
        if(!vh_map02_vram4_materialize(raw,sizeof raw,&regs,page,sizeof page,
                                        palette,sizeof palette,&stats)) {
            fprintf(stderr,"materializer rejected original PC inputs case=%u\n",t);
            return 2;
        }
        if(stats.decoded_texels!=65536u) return 3;
        for(y=0;y<256u;++y)
            for(x=0;x<256u;++x) {
                unsigned ix=sample_at(x,y);
                uint16_t actual=palette_word(ix);
                uint16_t expected=SampleTexture(&rc,regs.tpage,regs.clut,(int)x,(int)y);
                if(actual!=expected) {
                    fprintf(stderr,"PC/portable 4bpp mismatch case=%u at (%u,%u): "
                                   "index=%u actual=%u expected=%u\n",
                            t,x,y,ix,(unsigned)actual,(unsigned)expected);
                    return 4;
                }
                ++total;
            }
    }
    printf("{\"pixels_compared\":%u,\"scenarios\":%u,"
           "\"compiled_pc_sampletexture_matches\":true,"
           "\"real_gameplay_vram_verified\":false,"
           "\"ps1_hardware_pixels_verified\":false}\n",
           total,(unsigned)(sizeof cases/sizeof cases[0]));
    return 0;
}
"""


def compare(source: str, header: str, *, compiler="gcc") -> dict:
    extracted = extract_sample_functions(source)
    with tempfile.TemporaryDirectory(prefix="vh-map02-vram4-source-") as folder:
        root=Path(folder)
        (root/"map02_vram4_page.h").write_text(header,encoding="utf-8")
        (root/"verify.c").write_text(
            HARNESS.replace("{SOURCE}",extracted),encoding="utf-8")
        build=subprocess.run(
            [compiler,"-std=c11","-Wall","-Wextra","-Werror","-O2",
             str(root/"verify.c"),"-o",str(root/"verify")],
            capture_output=True,text=True,timeout=30)
        if build.returncode:
            raise ValueError("PC 4bpp differential compilation failed: "+build.stderr[-2200:])
        run=subprocess.run([str(root/"verify")],
                           capture_output=True,text=True,timeout=60)
        if run.returncode:
            raise ValueError("PC 4bpp sample comparison failed: "+run.stderr[-2200:])
        result=json.loads(run.stdout)
    if not (result["scenarios"]==32 and result["pixels_compared"]==2097152
            and result["compiled_pc_sampletexture_matches"]
            and not result["real_gameplay_vram_verified"]
            and not result["ps1_hardware_pixels_verified"]):
        raise ValueError("4bpp differential test contract changed")
    return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pc_raster",type=Path)
    p.add_argument("portable_header",type=Path)
    p.add_argument("--compiler",default="gcc")
    p.add_argument("--allow-modified-source",action="store_true")
    args=p.parse_args()
    try:
        raw=args.pc_raster.read_bytes()
        sha=git_blob_sha1(raw)
        if sha!=PINNED_RASTER_BLOB and not args.allow_modified_source:
            raise ValueError("pc_raster.c differs from pinned public Git blob")
        result=compare(raw.decode("utf-8"),
                       args.portable_header.read_text(encoding="utf-8"),
                       compiler=args.compiler)
        result["original_pc_git_blob_sha1"]=sha
        result["matches_pinned_pc_raster"]=sha==PINNED_RASTER_BLOB
    except (OSError,UnicodeError,ValueError,subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
