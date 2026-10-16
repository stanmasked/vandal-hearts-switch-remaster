#!/usr/bin/env python3
"""Compile actual pinned PC-port VectorNormalS and differential-test MAP02 Q12.

Uses only synthetic integer normals and original PUBLIC PC-port source.
Compares source function outputs and all 26-way source tie-break indices
with our Switch C classifier. This is not a hardware PS1 GTE proof:
PC_GTE_OP0 vertex truncation and MIPS GTE rounding remain separate.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from tools.prepare_map02_pcport import git_blob_sha1
from tools.audit_map02_direction_source import PINNED_PC_LIBGTE_BLOB

START = "int VectorNormalS(VECTOR *v0, SVECTOR *v1) {"
END = "/* SquareRoot0/SquareRoot12/csqrt:"
REQUIRED = (
    "double len = sqrt((double)v0->vx * v0->vx + (double)v0->vy * v0->vy + (double)v0->vz * v0->vz);",
    "if (len < 1.0)",
    "v1->vx = (short)((v0->vx * (double)ONE) / len);",
    "v1->vy = (short)((v0->vy * (double)ONE) / len);",
    "v1->vz = (short)((v0->vz * (double)ONE) / len);",
)

HOST = r"""
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#define ONE 4096
typedef struct { int32_t vx, vy, vz; } VECTOR;
typedef struct { int16_t vx, vy, vz, pad; } SVECTOR;
#include "map02_face_direction.h"
{UPSTREAM_VECTORNORMAL}

static int reference_index(SVECTOR n, uint8_t *out) {
    int best = -0x1000000;
    int chosen = 0;
    unsigned j;
    for (j = 0; j < 26; ++j) {
        VECTOR original = {
            vh_map02_directions[j].x,
            vh_map02_directions[j].y,
            vh_map02_directions[j].z
        };
        SVECTOR candidate = {0,0,0,0};
        int score;
        (void)VectorNormalS(&original, &candidate);
        score = n.vx * candidate.vx + n.vy * candidate.vy +
                n.vz * candidate.vz;
        if (score > best) {
            best = score;
            chosen = (int)j;
        } else if (score == best) {
            VECTOR prev = {
                vh_map02_directions[chosen].x,
                vh_map02_directions[chosen].y,
                vh_map02_directions[chosen].z
            };
            SVECTOR previous = {0,0,0,0};
            int proposed_ties = 0, previous_ties = 0;
            const int32_t normal_components[3] = {n.vx,n.vy,n.vz};
            const int32_t cand[3] = {candidate.vx,candidate.vy,candidate.vz};
            int32_t before[3];
            unsigned k;
            (void)VectorNormalS(&prev, &previous);
            before[0] = previous.vx;
            before[1] = previous.vy;
            before[2] = previous.vz;
            for (k=0; k<3; ++k) {
                int a = normal_components[k];
                int p = cand[k], b = before[k];
                proposed_ties += (a>0 && p>0) || (a<0 && p<0);
                proposed_ties += a == p;
                previous_ties += (a>0 && b>0) || (a<0 && b<0);
                previous_ties += a == b;
            }
            if (proposed_ties > previous_ties)
                chosen = (int)j;
        }
    }
    *out = (uint8_t)chosen;
    return 1;
}
static int check(int x,int y,int z) {
    VECTOR raw = {x,y,z};
    VhMap02Cross wide = {x,y,z};
    SVECTOR sdk = {0,0,0,0};
    int32_t port[3]={0,0,0};
    uint8_t a=255,b=255;
    if (x==0 && y==0 && z==0) return 1;
    (void)VectorNormalS(&raw,&sdk);
    if (!vh_map02_normal_q12(wide,port) ||
        sdk.vx != port[0] || sdk.vy != port[1] || sdk.vz != port[2]) {
        fprintf(stderr,"NORMAL_MISMATCH %d %d %d: sdk=%d,%d,%d port=%d,%d,%d\n",
                x,y,z,sdk.vx,sdk.vy,sdk.vz,port[0],port[1],port[2]);
        return 0;
    }
    reference_index(sdk,&a);
    if (!vh_map02_best_q12_direction(wide,&b) || a!=b) {
        fprintf(stderr,"INDEX_MISMATCH %d %d %d: sdk=%u port=%u\n",
                x,y,z,(unsigned)a,(unsigned)b);
        return 0;
    }
    return 1;
}
int main(void) {
    uint32_t state=0x19871016u;
    unsigned cases=0, i;
    static const int samples[][3] = {
        {1,1,1},{1,1,0},{1,-1,0},{0,1,-1},
        {-100,200,-300},{200,276,-107},{116,-159,-357},
        {-209,-156,82},{-95,65,36},{-396,-182,-130},
        {-126,-305,-256},{-203,103,-255},{354,247,135},
        {273,109,-91},{113,234,78},
        {32767,32767,32767},{-32768,32767,0},
        {65535,65535,1},{1,65535,65535}
    };
    for (i=0;i<sizeof(samples)/sizeof(samples[0]);++i) {
        if (!check(samples[i][0],samples[i][1],samples[i][2])) return 3;
        ++cases;
    }
    for (i=0;i<26;++i) {
        int x=vh_map02_directions[i].x;
        int y=vh_map02_directions[i].y;
        int z=vh_map02_directions[i].z;
        if (!check(x,y,z) || !check(100*x,100*y,100*z)) return 4;
        cases+=2;
    }
    for (i=0;i<2048;++i) {
        int v[3];
        unsigned j;
        for (j=0;j<3;++j) {
            state=state*1664525u+1013904223u;
            v[j]=(int)(state%20001u)-10000;
        }
        if (!check(v[0],v[1],v[2])) return 5;
        ++cases;
    }
    printf("{\"cases\":%u,\"vector_q12_matches_pc_port\":true,"
           "\"all_26_indices_match_pc_port\":true,"
           "\"ps1_hardware_gte_verified\":false}\n",cases);
    return 0;
}
"""


def extract_vectornormal(source: str) -> str:
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("pinned VectorNormalS boundaries changed")
    first, last = source.index(START), source.index(END)
    if last <= first:
        raise ValueError("VectorNormalS source function order changed")
    selected = source[first:last]
    for statement in REQUIRED:
        if statement not in selected:
            raise ValueError(f"VectorNormalS C source changed: {statement}")
    return selected


def compare(source: str, header: str, compiler: str = "gcc") -> dict:
    extracted = extract_vectornormal(source)
    if not shutil.which(compiler):
        raise ValueError(f"C compiler not found: {compiler}")
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "map02_face_direction.h").write_text(header, encoding="utf-8")
        (root / "check.c").write_text(
            HOST.replace("{UPSTREAM_VECTORNORMAL}", extracted), encoding="utf-8")
        build = subprocess.run(
            [compiler,"-std=c11","-O2","-Wall","-Wextra","-Werror",
             str(root/"check.c"),"-lm","-o",str(root/"check")],
            text=True,capture_output=True,timeout=30
        )
        if build.returncode:
            raise ValueError(f"native comparison build failed: {build.stderr[-1800:]}")
        run = subprocess.run([str(root/"check")],capture_output=True,
                             text=True,timeout=30)
        if run.returncode:
            raise ValueError(f"native VectorNormalS differential failure: {run.stderr[-1800:]}")
        return json.loads(run.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pc_libgte",type=Path)
    parser.add_argument("portable_header",type=Path)
    parser.add_argument("--compiler",default="gcc")
    parser.add_argument("--allow-modified-source",action="store_true")
    args=parser.parse_args()
    try:
        original = args.pc_libgte.read_bytes()
        sha=git_blob_sha1(original)
        if sha!=PINNED_PC_LIBGTE_BLOB and not args.allow_modified_source:
            raise ValueError("PC libgte.c differs from pinned public Git blob")
        report=compare(original.decode("utf-8"),
                       args.portable_header.read_text(encoding="utf-8"),
                       compiler=args.compiler)
        report["matches_pinned_pc_libgte"]=sha==PINNED_PC_LIBGTE_BLOB
        report["upstream_git_blob_sha1"]=sha
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as error:
        parser.error(str(error))
    print(json.dumps(report,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
