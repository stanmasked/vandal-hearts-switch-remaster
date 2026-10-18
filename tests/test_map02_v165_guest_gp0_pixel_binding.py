#!/usr/bin/env python3
"""v165: exact GP0 color/XY/size words at native gpulib and bound VRAM proof."""
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
sys.path.insert(0,str(ROOT/"tests"))
from test_map02_v164_guest_mips_halo import frontend_fixture
from tools.apply_map02_v164_guest_mips_halo import patch_frontend as patch_v164
from tools.apply_map02_v165_guest_gp0_pixel_binding import (
    GPU_APPEND,GPU_ENTRY,patch_gpu,patch_frontend,
)
from tools.make_map02_v121_mips_gp0_return_exe import COLORS,RECT_XY,RECT_SIZE


def gpulib_fixture() -> str:
    return r"""
void GPUwriteData(uint32_t data)
{
  gpu.cmd_buffer[gpu.cmd_len++] = HTOLE32(data);
#ifdef VH_MAP02_V66_PCSX_PROBE
  vh161_observe_gpu_queue(data);
#endif
}
"""


class GuestMipsGp0Vram165(unittest.TestCase):
    def test_original_guest_packet_source_and_order(self):
        self.assertEqual(COLORS,
            (0x600000ff,0x6000ff00,0x60ff0000,0x6000ffff,0x600000ff))
        self.assertEqual(RECT_XY,0x00a00028)
        self.assertEqual(RECT_SIZE,0x00040004)
        self.assertIn("vh161_observe_gpu_queue(data);",GPU_APPEND)
        gpu=patch_gpu(gpulib_fixture())
        self.assertLess(gpu.index("gpu.cmd_buffer[gpu.cmd_len++]"),
                        gpu.index("vh165_observe_guest_gp0(data);"))
        self.assertIn("word!=vh165_expected[vh165_words]",gpu)
        self.assertIn("gpu.cmd_buffer[gpu.cmd_len-1]!=HTOLE32(word)",gpu)
        with self.assertRaises(ValueError):
            patch_gpu(gpu)
        with self.assertRaises(ValueError):
            patch_gpu(gpulib_fixture().replace(GPU_APPEND,
                "  vh161_observe_wrong_gpu_queue(data);\n"))

    def test_frontend_binds_executed_words_before_pixel_readbacks(self):
        base="\textern int vh161_disarm_gpu_queue(void);\n"+frontend_fixture()
        source=patch_frontend(patch_v164(base))
        for exact in (
            "--vh165-mips-gp0-vram-bound",
            "vh121_mips_return_smoke=1;",
            "vh164_mips_raster_bounds=1;",
            "vh165_mips_gp0_vram_bound=1;",
            "vh165_arm_guest_gp0(vh165_expected_colors[phase]",
            "vh165_guest_gp0_words();",
            "vh165_guest_gp0_faults();",
            "vh165_disarm_guest_gp0();",
            "VH165_GP0_TRIPLET_REFUSED",
            "VH165_GUEST_MIPS_GP0_VRAM_BOUND_PASS",
            "phases=5 gp0_words=15 pixels_changed=80 border_unchanged=100",
            "host_draws=0 original_retail=0",
            "VH164_GUEST_MIPS_UNAI_VRAM_PASS",
        ):
            self.assertIn(exact,source)
        self.assertLess(source.index("vh165_arm_guest_gp0(",
                        source.index("if(vh121_mips_return_smoke) {")),
                        source.index("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);",
                                     source.index("for(unsigned int phase=0;phase<5u;phase++){")))
        self.assertLess(source.index("unsigned words=vh165_guest_gp0_words();"),
                        source.index("GPUFreeze_t freeze_state={0};"))
        self.assertLess(source.index("VH164_GUEST_MIPS_UNAI_VRAM_PASS"),
                        source.index("VH165_GUEST_MIPS_GP0_VRAM_BOUND_PASS"))
        with self.assertRaises(ValueError):
            patch_frontend(source)

    def test_compiled_real_append_and_negative_guest_gp0(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("compiler unavailable")
        from tools.apply_map02_v165_guest_gp0_pixel_binding import patch_gpu
        code=r"""
#include <stdint.h>
#include <stdio.h>
#define VH_MAP02_V66_PCSX_PROBE 1
#define CMD_BUFFER_LEN 48
#define HTOLE32(x) (x)
static struct {uint32_t cmd_buffer[CMD_BUFFER_LEN];int cmd_len;} gpu;
static void vh161_observe_gpu_queue(uint32_t word) {(void)word;}
""" + patch_gpu(gpulib_fixture()) + r"""
int main(void) {
    const uint32_t colors[5]={
        0x600000ffu,0x6000ff00u,0x60ff0000u,0x6000ffffu,0x600000ffu};
    GPUwriteData(0xe3000000u);
    if(vh165_guest_gp0_words() || vh165_guest_gp0_faults()) return 1;
    for(unsigned p=0;p<5u;p++){
        if(vh165_arm_guest_gp0(colors[p],0x00a00028u,0x00040004u)!=0)
            return 2;
        if(vh165_arm_guest_gp0(colors[p],0x00a00028u,0x00040004u)==0)
            return 3;
        GPUwriteData(colors[p]);
        GPUwriteData(0x00a00028u);
        GPUwriteData(0x00040004u);
        if(vh165_guest_gp0_words()!=3u || vh165_guest_gp0_faults())
            return 4;
        if(vh165_disarm_guest_gp0()!=0 ||
           vh165_disarm_guest_gp0()==0) return 5;
    }
    if(vh165_arm_guest_gp0(0x700000ffu,0x00a00028u,0x00040004u)==0 ||
       vh165_arm_guest_gp0(0x600000ffu,0x00a00029u,0x00040004u)==0 ||
       vh165_arm_guest_gp0(0x600000ffu,0x00a00028u,0x00040005u)==0)
        return 6;
    /* Wrong word must never be credited as guest packet. */
    if(vh165_arm_guest_gp0(colors[0],0x00a00028u,0x00040004u)!=0)
        return 7;
    GPUwriteData(colors[0]);
    GPUwriteData(0x00a00029u);
    GPUwriteData(0x00040004u);
    if(vh165_guest_gp0_words()!=1u || vh165_guest_gp0_faults()!=2u)
        return 8;
    if(vh165_disarm_guest_gp0()!=0) return 9;
    /* Extra GP0 is rejected even though the real queue appends it. */
    if(vh165_arm_guest_gp0(colors[0],0x00a00028u,0x00040004u)!=0)
        return 10;
    GPUwriteData(colors[0]);GPUwriteData(0x00a00028u);
    GPUwriteData(0x00040004u);GPUwriteData(0x600000ffu);
    if(vh165_guest_gp0_words()!=3u || vh165_guest_gp0_faults()!=1u)
        return 11;
    if(vh165_disarm_guest_gp0()!=0) return 12;
    /* Missing third packet word fails exact-three acceptance. */
    if(vh165_arm_guest_gp0(colors[0],0x00a00028u,0x00040004u)!=0)
        return 13;
    GPUwriteData(colors[0]);GPUwriteData(0x00a00028u);
    if(vh165_guest_gp0_words()!=2u || vh165_guest_gp0_faults())
        return 14;
    if(vh165_disarm_guest_gp0()!=0) return 15;
    puts("VH165_COMPILED_GPU_TRIPLET_PASS phases=5 words=15 missing_refused=1 wrong_word_refused=1 extra_refused=1 double_arm_refused=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh165-guest-gp0-") as td:
            p=Path(td)
            (p/"fixture.c").write_text(code)
            exe=p/"fixture"
            build=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(p/"fixture.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=40)
            self.assertEqual(build.returncode,0,build.stderr)
            out=subprocess.run([str(exe)],capture_output=True,
                               text=True,timeout=10)
            self.assertEqual(out.returncode,0,out.stdout+out.stderr)
            self.assertIn("VH165_COMPILED_GPU_TRIPLET_PASS",out.stdout)

    def test_full_native_gcc_clang_and_bad_magic(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        separate=(ROOT/".github/workflows/map02-v165-mips-gp0-pixel-binding.yml").read_text()
        for marker in (
            "apply_map02_v165_guest_gp0_pixel_binding",
            "test_map02_v165_guest_gp0_pixel_binding.py",
            "--vh165-mips-gp0-vram-bound",
            "VH165_GUEST_MIPS_GP0_VRAM_BOUND_PASS",
            "VH165_GP0_TRIPLET_REFUSED",
            "VH121_EXE_REFUSED",
        ):
            self.assertIn(marker,native)
        self.assertIn("test_map02_v164_guest_mips_halo.py",separate)
        self.assertIn("original_retail_executed=0",separate)


if __name__=="__main__":
    unittest.main()
