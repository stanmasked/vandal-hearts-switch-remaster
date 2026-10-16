#!/usr/bin/env python3
"""Differential-test portable MAP02 RTPT/NCLIP/RTPS/AVSZ4 against compiled
functions extracted from exact pinned public PC-port libgte.c.

Synthetic camera/vertex fixtures only; not actual MAP02 camera or hardware.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from tools.prepare_map02_pcport import git_blob_sha1
from tools.audit_map02_direction_source import PINNED_PC_LIBGTE_BLOB

FUNCTIONS = (
    "static int Sat16(int v, int lm) {",
    "static unsigned int SatU16(int v) {",
    "static void BuildUnrTable(void) {",
    "static int CountLeadingZeroes16(unsigned int sz) {",
    "static unsigned int UnrDivide(unsigned short H, unsigned short SZ3) {",
    "static void TransformOne(short vx, short vy, short vz) {",
    "void PC_GTE_RTPS(void) {",
    "void PC_GTE_RTPT(void) {",
    "void PC_GTE_NCLIP(void) {",
    "void PC_GTE_AVSZ4(void) {",
)
REQUIRED = (
    "g.sz0 = g.sz1; g.sz1 = g.sz2; g.sz2 = g.sz3;",
    "g.sz3 = (unsigned short)SatU16(mac3);",
    "n = UnrDivide((unsigned short)g.h, g.sz3);",
    "g.mac0 = (int)n * (int)g.ir1 + g.ofx;",
    "g.mac0 = (int)n * (int)g.ir2 + g.ofy;",
    "if (sx < -0x400)",
    "else if (sx > 0x3FF)",
    "g.mac0 = sx0 * sy1 + sx1 * sy2 + sx2 * sy0 - sx0 * sy2 - sx1 * sy0 - sx2 * sy1;",
    "g.mac0 = (int)g.zsf4 * (int)(g.sz0 + g.sz1 + g.sz2 + g.sz3);",
    "g.otz = (unsigned short)SatU16(g.mac0 >> 12);",
    "if (SZ3 == 0 || H >= (unsigned int)SZ3 * 2)",
    "s_unrTable[(d - 0x7FC0) >> 7] + 0x101;",
)

def extract_functions(libgte: str) -> str:
    parts = []
    for start in FUNCTIONS:
        if libgte.count(start) != 1:
            raise ValueError(f"PC projection function boundary changed: {start}")
        i = libgte.index(start)
        j = libgte.find("\n}\n", i)
        if j < 0:
            raise ValueError(f"PC projection ending brace missing: {start}")
        parts.append(libgte[i:j+2])
    out = "\n\n".join(parts)
    for anchor in REQUIRED:
        if anchor not in out:
            raise ValueError(f"PC projection arithmetic changed: {anchor}")
    return out

HOST = r"""
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "map02_projection.h"
typedef struct { short vx, vy, vz, pad; } PcSVector;
static struct {
    struct { short m[3][3]; } rt;
    int tr[3];
    int ofx, ofy;
    short h, dqa, zsf4;
    int dqb;
    PcSVector v0, v1, v2;
    unsigned short otz;
    short ir0, ir1, ir2, ir3;
    short sxy0[2], sxy1[2], sxy2[2];
    unsigned short sz0, sz1, sz2, sz3;
    int mac0, mac1, mac2, mac3;
    unsigned int flag;
} g;
static unsigned short s_unrTable[257];
static int s_unrTableInit = 0;
static struct { int sx, sy, ir1, ir2, ir3, sz3, n; } s_projRing[8];
static int s_projRingHead;

{EXTRACTED}

static int check(const VhMap02ProjectCamera *cam,
                 const VhMap02ProjectVertex v[4], unsigned index) {
    VhMap02ProjectFace portable;
    int area, i;
    uint32_t flags3;
    short x[4], y[4];
    unsigned short z[4];
    memset(&g, 0, sizeof g);
    for (i=0; i<3; ++i) {
        int j;
        g.tr[i] = cam->tr[i];
        for (j=0; j<3; ++j) g.rt.m[i][j] = cam->rt[i][j];
    }
    g.ofx=cam->ofx; g.ofy=cam->ofy;
    g.h=cam->h; g.zsf4=cam->zsf4;
    g.v0=(PcSVector){v[0].x,v[0].y,v[0].z,0};
    g.v1=(PcSVector){v[1].x,v[1].y,v[1].z,0};
    g.v2=(PcSVector){v[2].x,v[2].y,v[2].z,0};
    PC_GTE_RTPT();
    flags3=g.flag;
    x[0]=g.sxy0[0]; y[0]=g.sxy0[1]; z[0]=g.sz1;
    x[1]=g.sxy1[0]; y[1]=g.sxy1[1]; z[1]=g.sz2;
    x[2]=g.sxy2[0]; y[2]=g.sxy2[1]; z[2]=g.sz3;
    PC_GTE_NCLIP();
    area=g.mac0;
    if (!vh_map02_project_face(cam,v,1024,&portable)) {
        fprintf(stderr,"Portable projection rejected valid input %u\n",index);
        return 0;
    }
    if (area!=portable.nclip_mac0 ||
        ((area>0)!=portable.visible) ||
        portable.rtpt_flags!=flags3) {
        fprintf(stderr,"NCLIP / RTPT mismatch index=%u area=%d vs %d flags=%x vs %x\n",
                index,area,portable.nclip_mac0,flags3,portable.rtpt_flags);
        return 0;
    }
    if (area <= 0) return 1;
    g.v0=(PcSVector){v[3].x,v[3].y,v[3].z,0};
    PC_GTE_RTPS();
    x[3]=g.sxy2[0]; y[3]=g.sxy2[1]; z[3]=g.sz3;
    if (portable.rtps_flags!=g.flag) {
        fprintf(stderr,"RTPS flags mismatch %u: %x vs %x\n",
                index,g.flag,portable.rtps_flags);
        return 0;
    }
    PC_GTE_AVSZ4();
    if (portable.otz!=g.otz ||
        portable.depth!=(g.otz<5?5:g.otz) ||
        portable.ot_in_bounds!=((g.otz<5?5:g.otz)<=1024)) {
        fprintf(stderr,"AVSZ4/OT mismatch %u: %u vs %u\n",index,g.otz,portable.otz);
        return 0;
    }
    for (i=0; i<4; ++i) {
        int corner=(i==2?3:i==3?2:i);
        if (portable.gpu[corner].x!=x[i] ||
            portable.gpu[corner].y!=y[i] ||
            portable.sz[i]!=z[i]) {
            fprintf(stderr,"Projected screen/vertex mismatch case %u corner %d: "
                "upstream (%d,%d,z=%u), portable (%d,%d,z=%u)\n",
                index,i,x[i],y[i],z[i],
                portable.gpu[corner].x,portable.gpu[corner].y,portable.sz[i]);
            return 0;
        }
    }
    return 1;
}
int main(void) {
    uint32_t state=UINT32_C(0x19871016);
    unsigned cases=0,boundary_cases=0,i,j;
    VhMap02ProjectCamera c;
    VhMap02ProjectVertex v[4];
    memset(&c,0,sizeof c);
    c.rt[0][0]=4096; c.rt[1][1]=4096; c.rt[2][2]=4096;
    c.h=256; c.zsf4=256; c.ofx=160<<16; c.ofy=120<<16;
    v[0]=(VhMap02ProjectVertex){0,0,512};
    v[1]=(VhMap02ProjectVertex){100,0,512};
    v[2]=(VhMap02ProjectVertex){100,100,512};
    v[3]=(VhMap02ProjectVertex){0,100,512};
    if (!check(&c,v,cases++)) return 2;
    v[1]=(VhMap02ProjectVertex){0,100,512};
    v[3]=(VhMap02ProjectVertex){100,0,512};
    if (!check(&c,v,cases++)) return 2;
    v[0]=(VhMap02ProjectVertex){-32768,32767,0};
    v[1]=(VhMap02ProjectVertex){32767,0,1};
    v[2]=(VhMap02ProjectVertex){-32768,-32768,0};
    v[3]=(VhMap02ProjectVertex){32767,32767,32767};
    if (!check(&c,v,cases++)) return 2;
    /* Differential boundary coverage: UNR divide and screen XY saturation.
     * These synthetic cameras are compared against compiled pinned PC libgte. */
    {
        const short focal[] = {1,256,32767};
        const short z_values[] = {0,1,127,128,129,16383,16384,16385,32767};
        const int screen[] = {-1025,-1024,-1023,1022,1023,1024};
        unsigned hidx,zidx,sidx;
        for (hidx=0;hidx<3;++hidx)
            for (zidx=0;zidx<9;++zidx)
                for (sidx=0;sidx<6;++sidx) {
                    short z=z_values[zidx];
                    memset(&c,0,sizeof c);
                    c.rt[0][0]=4096; c.rt[1][1]=4096; c.rt[2][2]=4096;
                    c.h=focal[hidx]; c.zsf4=256;
                    c.ofx=screen[sidx]*65536;
                    c.ofy=screen[sidx]*65536;
                    v[0]=(VhMap02ProjectVertex){0,0,z};
                    v[1]=(VhMap02ProjectVertex){100,0,z};
                    v[2]=(VhMap02ProjectVertex){100,100,z};
                    v[3]=(VhMap02ProjectVertex){0,100,z};
                    if (!check(&c,v,cases++)) return 4;
                    ++boundary_cases;
                }
    }
    for (i=0; i<4096; ++i) {
        memset(&c,0,sizeof c);
        c.rt[0][0]=4096; c.rt[1][1]=4096; c.rt[2][2]=4096;
        c.h=(short)(64+(i%5)*128);
        c.zsf4=(short)(128+(i%5)*32);
        c.tr[2]=(int)(i%9)*80-320;
        c.ofx=(int)(i%320)<<16;
        c.ofy=(int)(i%240)<<16;
        /* Exercise negative axis/rotation signs without float math. */
        if (i&1u) {
            c.rt[0][0]=0; c.rt[0][2]=4096;
            c.rt[2][0]=-4096; c.rt[2][2]=0;
        }
        for (j=0; j<4; ++j) {
            uint32_t vv[3];
            unsigned k;
            for (k=0;k<3;++k) {
                state=state*UINT32_C(1664525)+UINT32_C(1013904223);
                vv[k]=state;
            }
            v[j].x=(short)((int)(vv[0]%2049u)-1024);
            v[j].y=(short)((int)(vv[1]%2049u)-1024);
            v[j].z=(short)((int)(vv[2]%3073u)-512);
        }
        if (!check(&c,v,cases++)) return 3;
    }
    printf("{\"cases\":%u,\"boundary_cases\":%u,\"compiled_pc_rtpt_nclip_rtps_avsz4_matches\":true,"
           "\"ps1_hardware_gte_verified\":false}\n",cases,boundary_cases);
    return 0;
}
"""

def compare(source: str, header: str, compiler: str = "gcc") -> dict:
    extracted = extract_functions(source)
    with tempfile.TemporaryDirectory(prefix="vh-map02-projection-") as folder:
        root = Path(folder)
        (root / "map02_projection.h").write_text(header, encoding="utf-8")
        (root / "check.c").write_text(
            HOST.replace("{EXTRACTED}", extracted), encoding="utf-8")
        built = subprocess.run(
            [compiler, "-std=c11", "-O2", "-fwrapv", "-Wall", "-Wextra",
             "-Werror", str(root / "check.c"), "-o", str(root / "check")],
            capture_output=True, text=True, timeout=30)
        if built.returncode:
            raise ValueError(f"PC projection comparison build failed: {built.stderr[-2500:]}")
        run = subprocess.run(
            [str(root / "check")], capture_output=True,text=True,timeout=30)
        if run.returncode:
            raise ValueError(f"PC projection mismatch: {run.stderr[-2500:]}")
        report = json.loads(run.stdout)
    if (report["cases"] != 4261 or report["boundary_cases"] != 162 or
        not report["compiled_pc_rtpt_nclip_rtps_avsz4_matches"] or
        report["ps1_hardware_gte_verified"]):
        raise ValueError("PC projection comparison contract changed")
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pc_libgte", type=Path)
    parser.add_argument("portable_header", type=Path)
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--allow-modified-source",action="store_true")
    args=parser.parse_args()
    try:
        raw=args.pc_libgte.read_bytes()
        sha=git_blob_sha1(raw)
        if sha!=PINNED_PC_LIBGTE_BLOB and not args.allow_modified_source:
            raise ValueError("PC libgte.c differs from pinned upstream source blob")
        report=compare(raw.decode("utf-8"),
                       args.portable_header.read_text(encoding="utf-8"),
                       compiler=args.compiler)
        report["matches_pinned_pc_libgte"] = sha==PINNED_PC_LIBGTE_BLOB
        report["upstream_git_blob_sha1"] = sha
    except (OSError,UnicodeError,ValueError,subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
