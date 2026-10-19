#!/usr/bin/env python3
"""v174: read-silent genuine MIPS VBlank wait fixture and native refusal."""
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
from tools.apply_map02_v173_vblank_quiet_mmio import patch_memory as v173_mem
from tools.apply_map02_v174_vblank_read_quiet import (
    patch_memory,patch_frontend,read_provenance_oracle,read_sentinel
)
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

def fake_mem():
    return """u32 psxMemRead32(psxRegisters *regs, u32 mem) {
 (void)regs;(void)mem;
 return 0;
}
void vh140_mmio_enable(unsigned mutate_expected) {
 (void)mutate_expected;
}
void psxMemWrite32(psxRegisters *regs,u32 mem,u32 value){
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
}
"""

def fake_front():
    return ('\tint vh173_mips_vblank_quiet_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh173-mips-vblank-quiet"))\n'
            '\tif (loadst_f) {\n')

class NativeVBlankReadQuiet174(unittest.TestCase):
    def test_unmodified_self_authored_wait_and_mips_lw_mutation(self):
        data,stops,starts,wait_pc,ops=build()
        idx=(wait_pc-START)//4
        self.assertEqual(len(stops),4)
        self.assertEqual(len(starts),4)
        self.assertEqual(ops[idx:idx+512],(0,)*512)
        self.assertEqual(data[0x4c:0x54],b"VH78SYN!")
        self.assertEqual(0x8d090000,(0x23<<26)|(8<<21)|(9<<16))

    def test_read_only_32bit_guest_gpu_read_sentinel_uses_real_memory_accessor(self):
        src=patch_memory(v173_mem(fake_mem()))
        for needle in (
            "u32 psxMemRead32(psxRegisters *regs, u32 mem)",
            "vh174_observe_wait_read(mem);",
            "vh174_arm_wait_read(unsigned phase)",
            "vh174_wait_read_faults(void)",
            "physical==0x1f801810u || physical==0x1f801814u",
            "vh173_wait_active",
        ):
            self.assertIn(needle,src)
        self.assertLess(src.index("vh174_observe_wait_read(mem);"),
                        src.index("(void)regs;(void)mem;"))
        self.assertNotIn("GPUwriteData(",read_sentinel())
        self.assertNotIn("psxRegs.cycle=",read_sentinel())
        with self.assertRaises(ValueError):patch_memory(src)
        with self.assertRaises(ValueError):patch_memory(fake_mem())

    def test_negative_and_positive_ordering_before_pixel_readback(self):
        front=patch_frontend(fake_front())
        oracle=read_provenance_oracle()
        self.assertIn("if(vh174_mips_vblank_read_quiet_smoke) {",oracle)
        self.assertNotIn("if(vh173_mips_vblank_quiet_smoke) {",oracle)
        self.assertIn("--vh174-mips-vblank-read-quiet",front)
        for needle in (
            "--vh174-mips-vblank-read-quiet",
            "vh174_arm_wait_read(phase)!=0",
            "vh174_wait_read_faults();",
            "VH174_VBLANK_WAIT_READ_REFUSED",
            "VH174_GUEST_MIPS_VBLANK_READ_QUIET_PASS",
            "VH173_GUEST_MIPS_VBLANK_QUIET_PASS",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
            "GPU_freeze(1,&state,&vram)",
            "original_retail=0",
        ):
            self.assertIn(needle,front)
        self.assertLess(oracle.index("vh173_arm_wait_quiet(phase)!=0"),
                        oracle.index("vh174_arm_wait_read(phase)!=0"))
        self.assertLess(oracle.index("vh174_wait_read_faults();"),
                        oracle.index("vh173_disarm_wait_quiet(phase);"))
        self.assertLess(oracle.index("VH174_VBLANK_WAIT_READ_REFUSED"),
                        oracle.index("GPU_freeze(1,&state,&vram)"))
        with self.assertRaises(ValueError):patch_frontend(front)

    def test_gcc_clang_compiled_clean_four_windows_and_bad_gpu_reads(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("compiler unavailable")
        c=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v){
 (void)r;(void)a;(void)v;
}
""" + patch_memory(v173_mem(fake_mem())) + r"""
int main(void) {
    psxRegisters regs={0};
    if(vh174_arm_wait_read(0u)==0)return 1;
    if(vh173_arm_wait_quiet(4u)==0)return 2;
    for(unsigned p=0;p<4u;p++){
       if(vh173_arm_wait_quiet(p)!=0)return 3;
       if(vh174_arm_wait_read((p+1u)%4u)==0)return 4;
       if(vh174_arm_wait_read(p)!=0)return 5;
       psxMemRead32(&regs,0x80011000u+p*4u);
       psxMemRead32(&regs,0x1f801820u);
       if(vh174_wait_read_faults()!=0u ||
          vh173_wait_mmio_faults()!=0u ||
          vh173_disarm_wait_quiet(p)!=0)return 6;
    }
    if(vh173_arm_wait_quiet(0u)!=0 ||
       vh174_arm_wait_read(0u)!=0)return 7;
    psxMemRead32(&regs,0x1f801810u);
    psxMemRead32(&regs,0xbf801814u);
    if(vh174_wait_read_faults()!=2u ||
       vh173_wait_mmio_faults()!=0u ||
       vh173_disarm_wait_quiet(0u)!=0)return 8;
    if(vh173_arm_wait_quiet(1u)!=0 ||
       vh174_arm_wait_read(1u)!=0)return 9;
    psxMemRead32(&regs,0x9f801810u);
    if(vh174_wait_read_faults()!=1u ||
       vh173_disarm_wait_quiet(0u)==0 ||
       vh173_disarm_wait_quiet(1u)!=0)return 10;
    puts("VH174_COMPILED_GPU_READ_QUIET_PASS windows=4 good_reads=0 bad_gp0=1 bad_gp1=1 alias_refused=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh174-read-") as tmp:
            d=Path(tmp);(d/"fixture.c").write_text(c)
            exe=d/"fixture"
            res=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(d/"fixture.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(res.returncode,0,res.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn("VH174_COMPILED_GPU_READ_QUIET_PASS",run.stdout)

    def test_real_pinned_native_negative_lw_workflow(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v174-vblank-read-quiet.yml").read_text()
        for needle in (
            "apply_map02_v174_vblank_read_quiet",
            "test_map02_v174_vblank_read_quiet.py",
            "--vh174-mips-vblank-read-quiet",
            "V174_SYNTHETIC.EXE",
            "V174_BAD_WAIT_LW.EXE",
            "VH174_GUEST_MIPS_VBLANK_READ_QUIET_PASS",
            "VH174_VBLANK_WAIT_READ_REFUSED",
        ):
            self.assertIn(needle,native)
        self.assertIn("test_map02_v173_vblank_quiet_mmio.py",own)
        self.assertIn("original_retail_executed=0",own)

if __name__=="__main__":
    unittest.main()
