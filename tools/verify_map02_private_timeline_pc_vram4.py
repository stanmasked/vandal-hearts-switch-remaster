#!/usr/bin/env python3
"""Private per-submission PC SampleTexture ↔ portable 4bpp source arithmetic.

A local *consistency* test for verified owner-supplied MAP02 GPU/VRAM timeline.
The referenced public PC source is pinned, but neither this program nor the
timeline validator authenticates genuine retail gameplay or PS1 GPU output.
No owned snapshot, texture byte, palette, coordinate or private path is emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess
import tempfile

from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_frame_bundle import (
    EVENT_LIMIT, VRAM_BYTES, fields, parse_json, sha_check,
)
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_vram_timeline import read_events, verify_timeline
from tools.verify_map02_pc_vram4_equivalence import (
    PINNED_RASTER_BLOB, extract_sample_functions,
)
from tools.prepare_map02_pcport import git_blob_sha1

SCHEMA = "vh.map02.private-timeline-pc-vram4-parity.v1"
OK = b"VH_MAP02_PRIVATE_PC_VRAM4_PASS\n"
PUBLIC_SOURCE_LIMIT = 2 * 1024 * 1024

HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "source/map02_vram4_page.h"

typedef struct { int twMaskX, twMaskY, twOffX, twOffY; } RenderCtx;
static unsigned short s_vram[512][1024];
static uint8_t vram[VH_MAP02_VRAM_BYTES];
static uint8_t atlas[VH_MAP02_VRAM4_ATLAS_BYTES];
static uint8_t clut[VH_MAP02_VRAM4_CLUT_BYTES];

{FUNCTIONS}

static unsigned get32(const unsigned char *p) {
    return (unsigned)p[0] | ((unsigned)p[1]<<8) |
           ((unsigned)p[2]<<16) | ((unsigned)p[3]<<24);
}
int main(void) {
    unsigned char meta[40];
    unsigned r[10];
    unsigned i, x, y;
    VhMap02Vram4Registers regs;
    VhMap02Vram4PageStats stats;
    RenderCtx ctx;
    if (fread(meta,1,sizeof meta,stdin)!=sizeof meta) return 2;
    for(i=0;i<10;++i) r[i]=get32(meta+i*4u);
    regs=(VhMap02Vram4Registers){(int)r[0],(int)r[1],
        (int)r[2],(int)r[3],(int)r[4],(int)r[5]};
    if (r[6]>255u || r[7]>255u || r[8]<1u || r[9]<1u ||
        r[8]>255u-r[6] || r[9]>255u-r[7]) return 3;
    if (fread(vram,1,sizeof vram,stdin)!=sizeof vram ||
        fgetc(stdin)!=EOF) return 4;
    for(i=0;i<512u*1024u;++i)
        s_vram[i/1024u][i%1024u]=(unsigned short)(
            (unsigned)vram[i*2u] | ((unsigned)vram[i*2u+1u]<<8));
    if (!vh_map02_vram4_materialize(vram,sizeof vram,&regs,atlas,sizeof atlas,
                                     clut,sizeof clut,&stats) ||
        stats.decoded_texels!=65536u) return 5;
    ctx=(RenderCtx){regs.mask_x,regs.mask_y,regs.offset_x,regs.offset_y};
    /* Compare the ENTIRE separately materialized page, not only probes.
       Also require every FT4 crop coordinate to remain in that page. */
    for(y=0;y<256u;++y) for(x=0;x<256u;++x) {
        unsigned idx=((unsigned)atlas[y*128u+x/2u]>>((x&1u)*4u))&15u;
        unsigned p=idx*2u;
        unsigned actual=(unsigned)clut[p] | ((unsigned)clut[p+1u]<<8);
        unsigned expected=SampleTexture(&ctx,regs.tpage,regs.clut,(int)x,(int)y);
        if (actual!=expected) return 6;
    }
    for(y=r[7];y<=r[7]+r[9];++y)
        for(x=r[6];x<=r[6]+r[8];++x) {
            unsigned idx=((unsigned)atlas[y*128u+x/2u]>>((x&1u)*4u))&15u;
            unsigned actual=(unsigned)clut[idx*2u] |
                            ((unsigned)clut[idx*2u+1u]<<8);
            if (actual!=SampleTexture(&ctx,regs.tpage,regs.clut,(int)x,(int)y))
                return 7;
        }
    if (fwrite("VH_MAP02_PRIVATE_PC_VRAM4_PASS\n",1,31,stdout)!=31)
        return 8;
    return 0;
}
"""


def make_harness(public_source: bytes, *, portable_header: str | None = None) -> str:
    if git_blob_sha1(public_source) != PINNED_RASTER_BLOB:
        raise ValueError("public PC raster is not the pinned Git blob")
    functions = extract_sample_functions(public_source.decode("utf-8"))
    source = HARNESS.replace("{FUNCTIONS}", functions)
    if portable_header is not None:
        # Test-only explicit mutation of the portable implementation; never
        # modify the checked-out repository header in-place.
        needle = '#include "source/map02_vram4_page.h"'
        if source.count(needle) != 1:
            raise ValueError("portable header insertion boundary missing")
        source = source.replace(needle, portable_header)
    return source


def snapshot_inputs(root: Path, count: int) -> tuple:
    names = ("timeline.json", "map02.decoded.bin", "gpu-events.jsonl")
    names += tuple(f"gpu-vram-{i:03d}.bin" for i in range(count))
    max_size = {
        "timeline.json": 65536,
        "map02.decoded.bin": 616 * 304,
        "gpu-events.jsonl": EVENT_LIMIT,
    }
    return tuple(
        private_file(
            root, name, _with_identity=True,
            expected=VRAM_BYTES if name.startswith("gpu-vram-") else None,
            max_bytes=max_size.get(name),
        )
        for name in names
    )


def verify_private_timeline(
    directory: Path, pinned_raster: Path, *, compiler: str = "gcc",
    portable_header: str | None = None,
) -> dict:
    root = _private_directory(directory)
    raster = Path(pinned_raster).absolute()
    if raster.is_symlink() or not raster.is_file() or raster.stat().st_size > PUBLIC_SOURCE_LIMIT:
        raise ValueError("pinned public PC raster unavailable")
    public = raster.read_bytes()
    source = make_harness(public, portable_header=portable_header)

    # Pin the manifest/event bytes + inode metadata before expensive original
    # GTE, source-coordinate and per-submission snapshot validation.
    initial_manifest = private_file(root, "timeline.json", max_bytes=65536)
    manifest = parse_json(initial_manifest, "timeline.json")
    fields(manifest, ("schema","frame","ot_size","pc_source_commit",
                      "decoded_map_sha256","events_sha256","snapshots"),
           "timeline.json", optional=("pc_game_binary_sha256",))
    descriptions = manifest["snapshots"]
    if type(descriptions) is not list or not 1 <= len(descriptions) <= 32:
        raise ValueError("private timeline requires 1–32 submissions")
    prior = snapshot_inputs(root, len(descriptions))
    if prior[0][0] != initial_manifest:
        raise ValueError("timeline manifest changed during acquisition")

    timeline = verify_timeline(root, compiler=compiler)
    if (timeline["submitted_faces_checked"] != len(descriptions) or
            timeline["snapshots_sha256_verified"] != len(descriptions)):
        raise ValueError("source/GTE/VRAM verification count changed")
    events = read_events(prior[2][0])
    if len(events) != len(descriptions):
        raise ValueError("event/snapshot count changed")
    for i, entry in enumerate(descriptions):
        sha_check(prior[3+i][0], entry["sha256"], "captured VRAM snapshot")

    root_code = Path(__file__).resolve().parent.parent
    checked = 0
    with tempfile.TemporaryDirectory(prefix="vh-map02-private-vram4-") as temp:
        source_path = Path(temp) / "checker.c"
        executable = Path(temp) / "checker"
        source_path.write_text(source, encoding="utf-8")
        build = subprocess.run(
            [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
             "-I", str(root_code), str(source_path), "-o", str(executable)],
            text=True, capture_output=True, timeout=45,
        )
        if build.returncode:
            raise ValueError("pinned PC / portable VRAM4 private checker unavailable")
        for i, event in enumerate(events):
            t = event["texture"]
            params = (
                t["tpage"], t["clut"], t["mask_x"], t["mask_y"],
                t["offset_x"], t["offset_y"], t["u"], t["v"], t["w"], t["h"]
            )
            data = struct.pack("<10I", *params) + prior[3+i][0]
            attempt = subprocess.run(
                [str(executable)], input=data, capture_output=True, timeout=45,
            )
            if attempt.returncode != 0 or attempt.stdout != OK or attempt.stderr:
                raise ValueError(
                    "compiled PC SampleTexture/portable materializer mismatch "
                    "for private submission"
                )
            checked += 1

    # Read sources a second time after BOTH expensive validators. This detects
    # inode replacement, length/mtime/ctime changes, and content changes.
    if snapshot_inputs(root, len(descriptions)) != prior:
        raise ValueError("private MAP02 timeline input changed during comparison")
    if (raster.read_bytes() != public or
            git_blob_sha1(public) != PINNED_RASTER_BLOB):
        raise ValueError("pinned public PC raster changed during comparison")
    return {
        "schema": SCHEMA,
        "submitted_faces": checked,
        "compiled_pc_source_4bpp_texels_compared": checked * 65536,
        "source_gte_and_snapshot_timeline_verified": True,
        "separate_vram_snapshot_per_primitive": True,
        "post_verification_input_stability_checked": True,
        "source_to_native_frame_join_authenticated": False,
        "real_ps1_hardware_pixels_authenticated": False,
        "original_map02_gameplay_authenticated": False,
        "private_game_bytes_emitted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_timeline_directory", type=Path)
    parser.add_argument("pinned_public_pc_raster", type=Path)
    parser.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    args = parser.parse_args()
    try:
        report = verify_private_timeline(
            args.private_timeline_directory, args.pinned_public_pc_raster,
            compiler=args.compiler,
        )
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        parser.error("private MAP02 PC raster/timeline verification unavailable")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
