#!/usr/bin/env python3
"""Verify per-FT4 GPU texture bindings against pinned public PC SampleTexture.

The source is pinned, the frame fixture is authored/synthetic, and the compiled
PC function is the independent per-texel oracle. This is not a retail PS1 run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from tools.prepare_map02_pcport import git_blob_sha1
from tools.verify_map02_pc_vram4_equivalence import (
    PINNED_RASTER_BLOB,
    extract_sample_functions,
)

FIXTURE_INCLUDE = '#include "../source/map02_vram4_frame.h"'
MAIN_ANCHOR = "int main(void) {"
EXPECTED = "VH_MAP02_PC_FT4_BINDING_PASS faces=3 samples=196608 clut_mutant=1 window_mutant=1 retail=0"

REFERENCE = r"""
typedef struct {
    int twMaskX, twMaskY, twOffX, twOffY;
} RenderCtx;
static unsigned short s_vram[512][1024];
/* The following source bodies come verbatim from the pinned PC port. */
{PINNED_FUNCTIONS}
"""

CHECK = r"""
/* Actual complete frame constructor: three independently observed faces,
 * two different CLUTs, three pages and a nontrivial GP0(E2) window.
 * This code intentionally reads the materialized PER-FACE buffers rather
 * than calling the standalone texture-page converter again.
 */
static unsigned verify_pinned_pc_face_bindings(int mutate) {
    VhMap02Vram4FrameInput in;
    VhMap02Vram4FrameWorkspace w;
    unsigned i, x, y, compared=0u;
    fixture();
    in=input();
    w=workspace();
    if (!vh_map02_vram4_frame_build(&in,&w)) return 0u;
    if (w.scene.count != N) return 0u;
    for (y=0u;y<512u;++y)
        for (x=0u;x<1024u;++x) {
            size_t off=((size_t)y*1024u+x)*2u;
            s_vram[y][x]=(unsigned short)(
                (unsigned)vram[off] | ((unsigned)vram[off+1u]<<8));
        }
    /* These deliberately tamper with the source record AFTER the frame
     * was materialized, violating its immutable binding contract. A robust
     * independent oracle must recognize both mismatches.
     */
    if (mutate == 1)
        observations[1].registers.clut=observations[0].registers.clut;
    if (mutate == 2)
        observations[2].registers.mask_x=0;
    for (i=0u;i<N;++i) {
        const VhMap02Vram4Registers *r=&observations[i].registers;
        const VhMap02TerrainQuad *quad=&prepared[i].quad;
        RenderCtx rc={r->mask_x,r->mask_y,r->offset_x,r->offset_y};
        if (w.scene.nodes[i].quad != quad ||
            w.scene.nodes[i].atlas4 != atlases+i*VH_MAP02_VRAM4_ATLAS_BYTES ||
            w.scene.nodes[i].clut_le != palettes+i*VH_MAP02_VRAM4_CLUT_BYTES ||
            quad->u != observations[i].face.u ||
            quad->v != observations[i].face.v ||
            quad->w != observations[i].face.w ||
            quad->h != observations[i].face.h)
            return 0u;
        for (y=0u;y<256u;++y)
            for (x=0u;x<256u;++x) {
                size_t off=i*VH_MAP02_VRAM4_ATLAS_BYTES+
                           (size_t)y*128u+x/2u;
                unsigned ix=((unsigned)atlases[off]>>((x&1u)*4u))&15u;
                size_t pal=i*VH_MAP02_VRAM4_CLUT_BYTES+ix*2u;
                uint16_t actual=(uint16_t)(
                    (unsigned)palettes[pal] | ((unsigned)palettes[pal+1u]<<8));
                uint16_t expected=SampleTexture(
                    &rc,r->tpage,r->clut,(int)x,(int)y);
                if (actual != expected) return 0u;
                ++compared;
            }
    }
    return compared;
}
"""

CALLS = r"""
    if (verify_pinned_pc_face_bindings(0) != 196608u) return 81;
    if (verify_pinned_pc_face_bindings(1) != 0u) return 82;
    if (verify_pinned_pc_face_bindings(2) != 0u) return 83;
    puts("VH_MAP02_PC_FT4_BINDING_PASS faces=3 samples=196608 clut_mutant=1 window_mutant=1 retail=0");
"""


def make_harness(raster_text: str, fixture_text: str) -> str:
    functions = extract_sample_functions(raster_text)
    if fixture_text.count(FIXTURE_INCLUDE) != 1:
        raise ValueError("frame fixture header boundary is not unique")
    if fixture_text.count(MAIN_ANCHOR) != 1:
        raise ValueError("frame fixture entrypoint boundary is not unique")
    if fixture_text.count("static void fixture(void) {") != 1:
        raise ValueError("frame fixture constructor boundary is not unique")
    if fixture_text.count("static uint8_t vram[VH_MAP02_VRAM_BYTES];") != 1:
        raise ValueError("frame fixture VRAM storage boundary is not unique")
    header = (
        '#include "source/map02_vram4_frame.h"\n'
        + REFERENCE.replace("{PINNED_FUNCTIONS}", functions)
    )
    result = fixture_text.replace(FIXTURE_INCLUDE, header)
    result = result.replace(
        MAIN_ANCHOR, CHECK + "\n" + MAIN_ANCHOR + "\n" + CALLS, 1
    )
    return result


def verify(raster: Path, fixture: Path, *, compiler: str) -> dict:
    raw = raster.read_bytes()
    if git_blob_sha1(raw) != PINNED_RASTER_BLOB:
        raise ValueError("original PC raster source is not the pinned Git blob")
    root = Path(__file__).resolve().parent.parent
    if fixture.resolve() != (root / "tests/test_map02_vram4_frame.c").resolve():
        raise ValueError("frame test is not the reviewed local source fixture")
    source = make_harness(
        raw.decode("utf-8"), fixture.read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="vh-map02-ft4-pc-binding-") as tmp:
        src = Path(tmp) / "verify.c"
        exe = Path(tmp) / "verify"
        src.write_text(source, encoding="utf-8")
        build = subprocess.run(
            [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
             "-I", str(root), str(src), "-o", str(exe), "-lm"],
            text=True, capture_output=True, timeout=45,
        )
        if build.returncode:
            raise ValueError(
                "source-pinned per-FT4 comparison failed to compile: "
                + build.stderr[-1600:]
            )
        run = subprocess.run(
            [str(exe)], text=True, capture_output=True, timeout=90,
        )
        if run.returncode or run.stdout.count(EXPECTED) != 1:
            raise ValueError(
                "source-pinned FT4/CLUT/E2 comparisons or mutants failed: "
                + run.stderr[-600:] + " exit=" + str(run.returncode)
            )
    return {
        "pinned_pc_raster_blob_sha1": PINNED_RASTER_BLOB,
        "authored_frame_faces": 3,
        "compared_source_reference_texels": 196608,
        "clut_identity_mutation_rejected": True,
        "texture_window_mutation_rejected": True,
        "full_retail_map02_frame_authenticated": False,
        "real_ps1_vram_authenticated": False,
        "physical_ps1_equivalence_proven": False,
        "marker": EXPECTED,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pc_raster", type=Path)
    parser.add_argument("reviewed_frame_fixture", type=Path)
    parser.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    args = parser.parse_args()
    try:
        outcome = verify(
            args.pinned_pc_raster, args.reviewed_frame_fixture,
            compiler=args.compiler,
        )
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        parser.error("pinned synthetic MAP02 FT4 texture binding verification failed")
    print(json.dumps(outcome, sort_keys=True))


if __name__ == "__main__":
    main()
