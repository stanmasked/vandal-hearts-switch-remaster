#!/usr/bin/env python3
"""v173: ensure interpreted MIPS VBlank waits contain no guest GPU MMIO writes."""
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
from tools.apply_map02_v173_vblank_quiet_mmio import (
    validated_guest_wait,native_mmio_quiet_observer,patch_memory,patch_frontend
)
from tools.make_map02_v78_vblank_mips_exe import build,WAIT_NOPS
from tools.make_map02_v70_synthetic_psx_exe import START,sw


def fake_mem():
    return """void vh140_mmio_enable(unsigned mutate_expected) {
 (void)mutate_expected;
}
void psxMemWrite32(psxRegisters *regs,u32 mem,u32 value){
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
}
"""


def fake_front():
    return ('\tint vh172_mips_vblank_vram_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh172-mips-real-vblank-vram"))\n'
            '\tif (loadst_f) {\n')


class GuestVBlankMMIOQuiet173(unittest.TestCase):
    def test_original_512_nop_mips_wait_remains_unmodified(self):
        idx,wait_pc=validated_guest_wait()
        raw,stops,starts,pc,program=build()
        self.assertEqual(wait_pc,pc)
        self.assertEqual(idx,(pc-START)//4)
        self.assertEqual(tuple(program[idx:idx+WAIT_NOPS]),(0,)*512)
        self.assertEqual(program[idx+512]>>26,2)
        self.assertEqual(program[idx+513],0)
        self.assertEqual(sw(9,0,8),0xad090000)
        self.assertEqual(raw[0x4c:0x54],b"VH78SYN!")
        self.assertEqual(len(raw),10240)

    def test_native_readonly_guest_gpu_mmio_wait_observer(self):
        source=patch_memory(fake_mem())
        for token in (
            "vh173_wait_active",
            "vh173_arm_wait_quiet(unsigned phase)",
            "vh173_observe_wait_mmio(u32 address)",
            "vh173_disarm_wait_quiet(unsigned phase)",
            "if(vh173_wait_active) vh173_observe_wait_mmio(mem);",
            "physical==0x1f801810u || physical==0x1f801814u",
        ):
            self.assertIn(token,source)
        self.assertLess(source.index("vh173_observe_wait_mmio(mem);"),
                        source.index("vh138_pc_observe(regs,mem,value);"))
        self.assertNotIn("GPUwriteData(",native_mmio_quiet_observer())
        self.assertNotIn("psxRegs.cycle=",native_mmio_quiet_observer())
        with self.assertRaises(ValueError):
            patch_memory(source)
        with self.assertRaises(ValueError):
            patch_memory(fake_mem().replace(
                "vh138_pc_observe(regs,mem,value);",
                "vh138_pc_observe(regs,mem,0);"))

    def test_readonly_sentinel_arms_after_guest_gpu_then_checks_before_vram(self):
        front=patch_frontend(fake_front())
        for required in (
            "--vh173-mips-vblank-quiet",
            "vh173_arm_wait_quiet(phase)!=0",
            "vh173_wait_mmio_faults();",
            "vh173_disarm_wait_quiet(phase);",
            "VH173_VBLANK_WAIT_MMIO_REFUSED",
            "vh173_quiet_windows!=4u",
            "VH173_GUEST_MIPS_VBLANK_QUIET_PASS",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
            "VH78_VBLANK_VRAM_PASS",
            "vh78_vblank_observed_count==entry_count",
            "GPU_freeze(1,&state,&vram)",
            "console_frame_asserted=0",
            "original_retail=0",
        ):
            self.assertIn(required,front)
        self.assertLess(front.index("vh171_disarm_guest_phase();"),
                        front.index("vh173_arm_wait_quiet(phase)!=0"))
        self.assertLess(front.index("vh173_arm_wait_quiet(phase)!=0"),
                        front.index("vh78_vblank_observed_count==entry_count"))
        self.assertLess(front.index("vh173_disarm_wait_quiet(phase);"),
                        front.index("GPU_freeze(1,&state,&vram)"))
        self.assertLess(front.index("VH173_VBLANK_WAIT_MMIO_REFUSED"),
                        front.index("VH173_GUEST_MIPS_VBLANK_QUIET_PASS"))
        with self.assertRaises(ValueError):patch_frontend(front)

    def test_gcc_clang_compiled_quiet_mmio_stages_and_negative_gpu_ports(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("C compiler unavailable")
        c=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v){
    (void)r;(void)a;(void)v;
}
""" + patch_memory(fake_mem()) + r"""
int main(void) {
    psxRegisters cpu={0};
    if(vh173_arm_wait_quiet(4u)==0)return 1;
    unsigned good_windows=0;
    for(unsigned p=0;p<4;p++){
        if(vh173_arm_wait_quiet(p)!=0 || vh173_arm_wait_quiet(p)==0)
            return 2;
        psxMemWrite32(&cpu,0x80011000u+p*4u,0x77010001u+p);
        psxMemWrite32(&cpu,0x1f801820u,0xa0000000u);
        if(vh173_wait_mmio_faults()!=0u || vh173_disarm_wait_quiet(p)!=0)
            return 3;
        good_windows++;
    }
    if(good_windows!=4 || vh173_disarm_wait_quiet(3u)==0)return 4;
    if(vh173_arm_wait_quiet(0u)!=0)return 5;
    psxMemWrite32(&cpu,0x1f801810u,0x600000ffu);
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    if(vh173_wait_mmio_faults()!=2u ||
       vh173_disarm_wait_quiet(0u)!=0)return 6;
    if(vh173_arm_wait_quiet(2u)!=0)return 7;
    psxMemWrite32(&cpu,0x1f801810u,0u);
    if(vh173_disarm_wait_quiet(1u)==0 ||
       vh173_wait_mmio_faults()!=1u ||
       vh173_disarm_wait_quiet(2u)!=0)return 8;
    puts("VH173_COMPILED_GPU_MMIO_QUIET_PASS windows=4 forbidden_good=0 gp0_refused=1 gp1_refused=1 wrong_phase_refused=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh173-mmio-quiet-") as tmp:
            d=Path(tmp);(d/"fixture.c").write_text(c);exe=d/"fixture"
            result=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(d/"fixture.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(result.returncode,0,result.stderr)
            actual=subprocess.run([str(exe)],capture_output=True,
                                  text=True,timeout=10)
            self.assertEqual(actual.returncode,0,actual.stdout+actual.stderr)
            self.assertIn("VH173_COMPILED_GPU_MMIO_QUIET_PASS",actual.stdout)

    def test_full_native_negative_sw_in_wait_pad_gate(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v173-vblank-quiet-mmio.yml").read_text()
        for needle in (
            "apply_map02_v173_vblank_quiet_mmio",
            "test_map02_v173_vblank_quiet_mmio.py",
            "--vh173-mips-vblank-quiet",
            "V173_SYNTHETIC.EXE",
            "V173_BAD_WAIT_SW.EXE",
            "VH173_GUEST_MIPS_VBLANK_QUIET_PASS",
            "VH173_VBLANK_WAIT_MMIO_REFUSED",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
        ):
            self.assertIn(needle,native)
        self.assertIn("test_map02_v172_mips_real_vblank_vram.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
