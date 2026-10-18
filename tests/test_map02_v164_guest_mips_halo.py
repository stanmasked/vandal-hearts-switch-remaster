#!/usr/bin/env python3
"""v164: exact VRAM deltas from real CPU-authored synthetic PS1 GP0 draws."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from tools.apply_map02_v121_pcsx_rearmed import oracle_source
from tools.apply_map02_v164_guest_mips_halo import (
    BASELINE,CLI,FLAG,MAIN,PASS,patch_frontend,halo_validator_c
)
from tools.make_map02_v121_mips_gp0_return_exe import (
    build,sw,COLORS,EXPECTED_PIXELS,SETUP,RECT_XY,RECT_SIZE
)


def frontend_fixture() -> str:
    _,stops,_,_=build()
    return MAIN+FLAG+CLI+oracle_source(stops)


class GuestMipsVramHalo164(unittest.TestCase):
    def test_source_authenticated_guest_mips_gpu_rectangles(self):
        image,stops,opcodes,starts=build()
        self.assertEqual(image[:8],b"PS-X EXE")
        self.assertEqual(image[0x4c:0x54],b"VH121SY!")
        self.assertEqual(len(stops),6)
        self.assertEqual(len(starts),6)
        self.assertEqual(sum(word==sw(9,0,8) for word in opcodes),
                         len(SETUP)+3*len(COLORS))
        self.assertEqual(len(COLORS),5)
        self.assertEqual(RECT_XY,(160<<16)|40)
        self.assertEqual(RECT_SIZE,(4<<16)|4)
        self.assertEqual(EXPECTED_PIXELS,
                         (0x001f,0x03e0,0x7c00,0x03ff,0x001f))

    def test_frontend_strict_isolation_halo_and_guest_only_path(self):
        patched=patch_frontend(frontend_fixture())
        for needle in (
            "--vh164-mips-vram-halo",
            "vh121_mips_return_smoke=1;",
            "vh164_mips_raster_bounds=1;",
            "VH164_MIXED_PROVENANCE_REFUSED",
            "VH164_MIPS_HALO_REFUSED phase=%u",
            "VH164_GUEST_MIPS_UNAI_VRAM_PASS",
            "rectangles=5 changed=80 border=100",
            "host_draws=0 original_retail=0",
            "vh164_check_mips_halo(vh164_previous,vram,",
            "setup_pixels[(159u+y)*1024u+39u+x]",
            "VH121_MIPS_GP0_RETURN_PASS",
        ):
            self.assertIn(needle,patched)
        self.assertLess(patched.index("setup_pixels[(159u+y)*1024u+39u+x]"),
                        patched.index("vh164_check_mips_halo(vh164_previous,vram,"))
        self.assertLess(patched.index("VH164_GUEST_MIPS_UNAI_VRAM_PASS"),
                        patched.index("VH121_MIPS_GP0_RETURN_PASS"))
        # The new raster assertion must observe guest-produced VRAM,
        # never add host-submitted GP0 draw words to this mode.
        body=patched[patched.index("if(vh121_mips_return_smoke) {"):]
        self.assertNotIn("GPU_writeDataMem(",body)
        self.assertNotIn("GPU_writeData(",body)
        with self.assertRaises(ValueError):
            patch_frontend(patched)
        with self.assertRaises(ValueError):
            patch_frontend(frontend_fixture().replace("VH121_VRAM_REFUSED",
                         "VH121_TAMPERED"))

    def test_compiled_pixel_halo_including_wrong_color_and_border(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("compiler unavailable")
        c=r"""
#include <stdint.h>
#include <stdio.h>
#define VH_MAP02_V66_PCSX_PROBE 1
""" + halo_validator_c() + r"""
static uint16_t vram[1024*512];
static uint16_t prev[36];
static void reset_before(void){
    for(unsigned y=0;y<6u;y++)
        for(unsigned x=0;x<6u;x++)
            prev[y*6u+x]=vram[(159u+y)*1024u+39u+x];
}
static void draw_rect(uint16_t color){
    for(unsigned y=160u;y<164u;y++)
        for(unsigned x=40u;x<44u;x++)
            vram[y*1024u+x]=color;
}
int main(void){
    const uint16_t phases[5]={0x001f,0x03e0,0x7c00,0x03ff,0x001f};
    unsigned changes=0u,border=0u;
    reset_before();
    for(unsigned phase=0u;phase<5u;phase++){
        draw_rect(phases[phase]);
        if(vh164_check_mips_halo(prev,vram,phases[phase],
                                  &changes,&border)!=0) return 1;
        if(changes!=(phase+1u)*16u ||
           border!=(phase+1u)*20u) return 2;
    }
    if(changes!=80u || border!=100u) return 3;
    /* No pixel changed: do not recredit the last red image. */
    if(vh164_check_mips_halo(prev,vram,0x001f,&changes,&border)==0)
        return 4;
    if(changes!=80u || border!=100u) return 5;
    /* A corrupted border pixel must always refuse. */
    draw_rect(0x03e0);
    vram[159u*1024u+39u]=0x7fffu;
    if(vh164_check_mips_halo(prev,vram,0x03e0,&changes,&border)==0)
        return 6;
    if(changes!=80u || border!=100u) return 7;
    vram[159u*1024u+39u]=0u;
    /* Wrong interior color is refused even when every pixel changed. */
    if(vh164_check_mips_halo(prev,vram,0x7c00,&changes,&border)==0)
        return 8;
    if(changes!=80u || border!=100u) return 9;
    if(vh164_check_mips_halo(0,vram,0x03e0,&changes,&border)==0)
        return 10;
    puts("VH164_COMPILED_GUEST_MIPS_HALO_PASS rectangles=5 changed=80 border=100 baseline_refused=1 wrong_color_refused=1 border_mutation_refused=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh164-mips-") as td:
            p=Path(td);(p/"h.c").write_text(c);exe=p/"h"
            result=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(p/"h.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(exe)],capture_output=True,
                                  text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn("VH164_COMPILED_GUEST_MIPS_HALO_PASS",
                          result.stdout)

    def test_full_native_gcc_clang_wiring_and_negative_mode(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone=(ROOT/".github/workflows/map02-v164-guest-mips-halo.yml").read_text()
        for marker in (
            "apply_map02_v164_guest_mips_halo",
            "test_map02_v164_guest_mips_halo.py",
            "--vh164-mips-vram-halo",
            "VH164_GUEST_MIPS_UNAI_VRAM_PASS",
            "VH164_MIXED_PROVENANCE_REFUSED",
            "VH121_MIPS_GP0_RETURN_PASS",
        ):
            self.assertIn(marker,native)
        self.assertIn("test_map02_v163_host_unai_rectangle.py",
                      standalone)
        self.assertIn("original_retail_executed=0",standalone)


if __name__=="__main__":
    unittest.main()
