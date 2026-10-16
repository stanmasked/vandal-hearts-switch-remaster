#!/usr/bin/env python3
"""Compare PC OP0 MAC math with compiled functions from pinned public libgte.c.

PC mode: first D vector 32-bit, second IR 16-bit, signed-int wrap32,
MAC readback (not saturated IR).  PS1 mode is *only* a signed-16
input and 32-bit MAC-readback model; no hardware GTE verification.
No game resource data is used or emitted.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from tools.prepare_map02_pcport import git_blob_sha1
from tools.audit_map02_direction_source import PINNED_PC_LIBGTE_BLOB

SIGNATURES = (
    "static int Sat16(int v, int lm) {",
    "void PC_GTE_LoadOPV1(void *v) {",
    "void PC_GTE_LoadOPV2(void *v) {",
    "void PC_GTE_OP0(void) {",
    "void PC_GTE_StoreLVNL(void *out) {",
)
REQUIRED = (
    "g.opvD[0] = src[0];",
    "g.opvD[1] = src[1];",
    "g.opvD[2] = src[2];",
    "g.ir1 = (short)src[0];",
    "g.ir2 = (short)src[1];",
    "g.ir3 = (short)src[2];",
    "g.mac1 = ir3 * d2 - ir2 * d3;",
    "g.mac2 = ir1 * d3 - ir3 * d1;",
    "g.mac3 = ir2 * d1 - ir1 * d2;",
    "g.ir1 = (short)Sat16(g.mac1, 0);",
    "g.ir2 = (short)Sat16(g.mac2, 0);",
    "g.ir3 = (short)Sat16(g.mac3, 0);",
    "o[0] = g.mac1; o[1] = g.mac2; o[2] = g.mac3;",
)

def extract_pc_op0(source: str) -> str:
    """Extract complete pinned C function bodies, rejecting changed anchors."""
    parts = []
    for signature in SIGNATURES:
        if source.count(signature) != 1:
            raise ValueError(f"PC OP0 source signature changed: {signature}")
        begin = source.index(signature)
        end = source.find("\n}\n", begin)
        if end == -1:
            raise ValueError(f"PC OP0 function boundary changed: {signature}")
        parts.append(source[begin:end + 2])
    extracted = "\n\n".join(parts)
    for statement in REQUIRED:
        if statement not in extracted:
            raise ValueError(f"PC OP0 arithmetic changed: {statement}")
    return extracted

HOST = r"""
#include <stdint.h>
#include <stdio.h>
#include "map02_op0_reference.h"

static struct {
    int opvD[3];
    short ir1, ir2, ir3;
    int mac1, mac2, mac3;
} g;

{EXTRACTED}

static unsigned cases, differences;
static int check(const int32_t a[3], const int32_t b[3]) {
    int aa[3] = {a[0],a[1],a[2]}, bb[3] = {b[0],b[1],b[2]};
    int original[3];
    VhMap02Op0Mac portable, hardware_inputs;
    unsigned diff;
    PC_GTE_LoadOPV1(aa);
    PC_GTE_LoadOPV2(bb);
    PC_GTE_OP0();
    PC_GTE_StoreLVNL(original);
    if (!vh_map02_op0_pc(a,b,&portable) ||
        !vh_map02_op0_ps1_registers(a,b,&hardware_inputs) ||
        original[0]!=portable.x || original[1]!=portable.y ||
        original[2]!=portable.z) {
        fprintf(stderr,
            "OP0_MISMATCH a=%d,%d,%d b=%d,%d,%d original=%d,%d,%d portable=%d,%d,%d\n",
            a[0],a[1],a[2],b[0],b[1],b[2],
            original[0],original[1],original[2],
            portable.x,portable.y,portable.z);
        return 0;
    }
    diff = (portable.x!=hardware_inputs.x) ||
           (portable.y!=hardware_inputs.y) ||
           (portable.z!=hardware_inputs.z);
    if (diff) ++differences;
    ++cases;
    return 1;
}

int main(void) {
    /* Includes signed vertex-difference extremes, wrap32 MAC, and IR cast. */
    static const int32_t inputs[][6] = {
        {2,3,5,7,11,13}, {65535,65535,0,-65535,0,65535},
        {65535,65535,65535,32767,-32768,32767},
        {-65535,0,65535,0,65535,-65535},
        {32767,-32768,0,-32768,32767,1},
        {-32768,32767,1,32767,-32768,2},
        {0,0,0,0,0,0}, {1,0,0,0,1,0},
        {32768,0,0,0,32768,1},
        {-65535,-65535,-65535,-32768,32767,-32768}
    };
    unsigned i,j;
    uint32_t state = UINT32_C(0x19871016);
    for (i=0;i<sizeof(inputs)/sizeof(inputs[0]);++i)
        if (!check(inputs[i],inputs[i]+3)) return 2;
    for (i=0;i<4096;++i) {
        int32_t a[3], b[3];
        for (j=0;j<3;++j) {
            state = state*UINT32_C(1664525)+UINT32_C(1013904223);
            a[j] = (int32_t)(state%UINT32_C(131071))-65535;
            state = state*UINT32_C(1664525)+UINT32_C(1013904223);
            b[j] = (int32_t)(state%UINT32_C(131071))-65535;
        }
        if (!check(a,b)) return 3;
    }
    if (!differences) {
        fputs("PS1-vs-PC input distinction was not exercised\n",stderr);
        return 4;
    }
    printf("{\"cases\":%u,\"compiled_pc_op0_mac_matches\":true,"
           "\"pc_vs_ps1_register_input_difference_cases\":%u,"
           "\"ps1_hardware_gte_verified\":false}\n",cases,differences);
    return 0;
}
"""

def compare(source: str, header: str, compiler: str = "gcc") -> dict:
    extracted = extract_pc_op0(source)
    with tempfile.TemporaryDirectory(prefix="vh-map02-op0-") as directory:
        root = Path(directory)
        (root / "map02_op0_reference.h").write_text(header, encoding="utf-8")
        (root / "check.c").write_text(
            HOST.replace("{EXTRACTED}", extracted), encoding="utf-8")
        built = subprocess.run(
            [compiler, "-std=c11", "-O2", "-fwrapv", "-Wall",
             "-Wextra", "-Werror", str(root / "check.c"),
             "-o", str(root / "check")],
            capture_output=True, text=True, timeout=30)
        if built.returncode:
            raise ValueError(f"compiled PC OP0 check failed: {built.stderr[-1800:]}")
        run = subprocess.run([str(root / "check")],
                             capture_output=True,text=True,timeout=30)
        if run.returncode:
            raise ValueError(f"PC OP0 MAC mismatch: {run.stderr[-1800:]}")
        report = json.loads(run.stdout)
    if report["cases"] != 4106 or not report["pc_vs_ps1_register_input_difference_cases"]:
        raise ValueError("PC OP0 comparison did not cover required cases")
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pc_libgte", type=Path)
    parser.add_argument("portable_header", type=Path)
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--allow-modified-source", action="store_true")
    args = parser.parse_args()
    try:
        original = args.pc_libgte.read_bytes()
        sha = git_blob_sha1(original)
        if sha != PINNED_PC_LIBGTE_BLOB and not args.allow_modified_source:
            raise ValueError("PC libgte.c differs from pinned public Git blob")
        report = compare(original.decode("utf-8"),
                         args.portable_header.read_text(encoding="utf-8"),
                         compiler=args.compiler)
        report["matches_pinned_pc_libgte"] = sha == PINNED_PC_LIBGTE_BLOB
        report["upstream_git_blob_sha1"] = sha
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
