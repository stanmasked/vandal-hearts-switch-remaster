#!/usr/bin/env python3
"""v176: native narrow GPU MMIO fixture / signed synthetic MIPS mutation gates."""
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
from tools.apply_map02_v174_vblank_read_quiet import patch_memory as v174_mem
from tools.apply_map02_v175_dual_gpu_read_ports import patch_memory as v175_mem
from tools.apply_map02_v176_narrow_gpu_mmio import (
    patch_memory, patch_frontend, narrow_oracle, narrow_observer
)
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

def fake_mem():
    return """u8 psxMemRead8(psxRegisters *regs, u32 mem) {
 (void)regs;(void)mem;
 return 0;
}
u16 psxMemRead16(psxRegisters *regs, u32 mem) {
 (void)regs;(void)mem;
 return 0;
}
u32 psxMemRead32(psxRegisters *regs, u32 mem) {
 (void)regs;(void)mem;
 return 0;
}
void psxMemWrite8(psxRegisters *regs,u32 mem,u32 value) {
 (void)regs;(void)mem;(void)value;
}
void psxMemWrite16(psxRegisters *regs,u32 mem,u32 value) {
 (void)regs;(void)mem;(void)value;
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
    return ('\tint vh175_mips_vblank_dual_ports_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh175-mips-vblank-dual-ports"))\n'
            '\tif (loadst_f) {\n')

def full_memory():
    return patch_memory(v175_mem(v174_mem(v173_mem(fake_mem()))))

class NarrowGPU176(unittest.TestCase):
    def test_four_real_mips_instructions_differ_by_exactly_one_wait_word(self):
        data,stops,starts,wait_pc,ops=build()
        i=(wait_pc-START)//4
        self.assertEqual(data[:8],b"PS-X EXE")
        self.assertEqual(data[0x4c:0x54],b"VH78SYN!")
        self.assertEqual(ops[i:i+512],(0,)*512)
        self.assertEqual(len(stops),4)
        self.assertEqual({
            "lb_gp1":(0x20<<26)|(8<<21)|(9<<16)|4,
            "lh_gp0":(0x21<<26)|(8<<21)|(9<<16),
            "sb_gp1":(0x28<<26)|(8<<21)|(9<<16)|4,
            "sh_gp0":(0x29<<26)|(8<<21)|(9<<16),
        },{"lb_gp1":0x81090004,"lh_gp0":0x85090000,
           "sb_gp1":0xa1090004,"sh_gp0":0xa5090000})

    def test_true_pcsx_memory_accessor_hooks_and_no_gpu_mutation(self):
        s=full_memory()
        for needle in (
            "vh176_observe_narrow(mem,0u,0u);",
            "vh176_observe_narrow(mem,1u,0u);",
            "vh176_observe_narrow(mem,0u,1u);",
            "vh176_observe_narrow(mem,1u,1u);",
            "vh176_arm_narrow(unsigned phase)",
            "vh176_disarm_narrow(unsigned phase)",
            "vh176_narrow_total(void)",
            "physical>0x1f801817u",
        ):
            self.assertIn(needle,s)
        self.assertLess(s.index("vh176_observe_narrow(mem,0u,0u);"),
                        s.index("(void)regs;(void)mem;"))
        self.assertNotIn("GPUwriteData(",narrow_observer())
        self.assertNotIn("psxRegs.cycle=",narrow_observer())
        with self.assertRaises(ValueError):patch_memory(s)
        with self.assertRaises(ValueError):patch_memory(fake_mem())

    def test_diagnostic_cli_and_early_refusal_while_preserving_v175(self):
        front=patch_frontend(fake_front())
        oracle=narrow_oracle()
        self.assertIn("if(vh176_mips_vblank_narrow_mmio_smoke) {",oracle)
        self.assertNotIn("if(vh175_mips_vblank_dual_ports_smoke) {",oracle)
        for t in ("--vh176-mips-vblank-narrow-mmio",
                  "VH176_NARROW_MMIO_REFUSED",
                  "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
                  "VH175_GUEST_MIPS_VBLANK_PORTS_PASS",
                  "VH174_GUEST_MIPS_VBLANK_READ_QUIET_PASS",
                  "VH173_GUEST_MIPS_VBLANK_QUIET_PASS",
                  "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
                  "GPU_freeze(1,&state,&vram)"):
            self.assertIn(t,front)
        self.assertLess(oracle.index("vh175_arm_read_ports(phase)!=0"),
                        oracle.index("vh176_arm_narrow(phase)!=0"))
        self.assertLess(oracle.index("vh176_disarm_narrow(phase);"),
                        oracle.index("vh175_disarm_read_ports(phase);"))
        self.assertLess(oracle.index("VH176_NARROW_MMIO_REFUSED"),
                        oracle.index("GPU_freeze(1,&state,&vram)"))
        with self.assertRaises(ValueError):patch_frontend(front)

    def test_compiled_gcc_clang_four_windows_and_all_eight_width_port_directions(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("C compiler unavailable")
        pre=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v){
 (void)r;(void)a;(void)v;
}
"""
        body=r"""
int main(void){
    psxRegisters regs={0};
    unsigned p;
    if(vh176_arm_narrow(0u)==0)return 1;
    for(p=0;p<4;p++){
        if(vh173_arm_wait_quiet(p)!=0 ||
           vh174_arm_wait_read(p)!=0 ||
           vh175_arm_read_ports(p)!=0 ||
           vh176_arm_narrow(p)!=0 ||
           vh176_arm_narrow(p)==0)return 2;
        psxMemRead8(&regs,0x80010200u);
        psxMemRead16(&regs,0x1f801820u);
        psxMemWrite8(&regs,0x80010208u,1u);
        psxMemWrite16(&regs,0x1f801822u,2u);
        if(vh176_narrow_total()!=0u ||
           vh176_disarm_narrow((p+1u)%4u)==0 ||
           vh176_disarm_narrow(p)!=0 ||
           vh176_disarm_narrow(p)==0 ||
           vh175_disarm_read_ports(p)!=0 ||
           vh174_disarm_wait_read(p)!=0 ||
           vh173_disarm_wait_quiet(p)!=0)return 3;
    }
    if(vh173_arm_wait_quiet(0u)!=0 ||
       vh174_arm_wait_read(0u)!=0 ||
       vh175_arm_read_ports(0u)!=0 ||
       vh176_arm_narrow(0u)!=0)return 4;
    psxMemRead8(&regs,0x1f801810u);
    psxMemRead8(&regs,0xbf801814u);
    psxMemRead16(&regs,0x9f801812u);
    psxMemRead16(&regs,0x1f801816u);
    psxMemWrite8(&regs,0x1f801811u,1u);
    psxMemWrite8(&regs,0x9f801815u,1u);
    psxMemWrite16(&regs,0xbf801810u,1u);
    psxMemWrite16(&regs,0x1f801814u,1u);
    if(vh176_narrow_total()!=8u || vh174_wait_read_faults()!=0u ||
       vh175_gp0_read_faults()!=0u || vh175_gp1_read_faults()!=0u ||
       vh173_wait_mmio_faults()!=0u)return 5;
    for(unsigned w=0;w<2;w++)for(unsigned d=0;d<2;d++)
        for(unsigned port=0;port<2;port++)
          if(vh176_narrow_count(w,d,port)!=1u)return 6;
    if(vh176_arm_narrow(0u)==0 || vh176_narrow_total()!=8u ||
       vh176_disarm_narrow(1u)==0 ||
       vh176_disarm_narrow(0u)!=0 ||
       vh175_disarm_read_ports(0u)!=0 ||
       vh174_disarm_wait_read(0u)!=0 ||
       vh173_disarm_wait_quiet(0u)!=0)return 7;
    puts("VH176_COMPILED_NARROW_MMIO_PASS windows=4 width8=4 width16=4 reads=4 writes=4 gp0=4 gp1=4 double_arm_refused=1 wrong_phase_refused=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh176-narrow-") as d:
            src=Path(d)/"fixture.c";exe=Path(d)/"fixture"
            src.write_text(pre+full_memory()+body)
            compiled=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(src),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            out=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(out.returncode,0,out.stdout+out.stderr)
            self.assertIn("VH176_COMPILED_NARROW_MMIO_PASS",out.stdout)

    def test_workflow_proves_real_native_narrow_mips_negative(self):
        guard=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v176-narrow-gpu-mmio.yml").read_text()
        for token in ("apply_map02_v176_narrow_gpu_mmio",
                      "test_map02_v176_narrow_gpu_mmio.py",
                      "--vh176-mips-vblank-narrow-mmio",
                      "V176_SYNTHETIC.EXE",
                      "V176_BAD_",
                      '"LB_GP1":0x81090004',
                      '"LH_GP0":0x85090000',
                      '"SB_GP1":0xa1090004',
                      '"SH_GP0":0xa5090000',
                      "VH176_NARROW_MMIO_REFUSED",
                      "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS"):
            self.assertIn(token,guard)
        self.assertIn("test_map02_v175_dual_gpu_read_ports.py",own)

if __name__=="__main__":
    unittest.main()
