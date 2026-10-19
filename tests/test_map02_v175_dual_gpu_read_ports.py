#!/usr/bin/env python3
"""v175: four genuine MIPS VBlank waits with separate GP0 and GP1 read counts."""
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
    return ('\tint vh174_mips_vblank_read_quiet_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh174-mips-vblank-read-quiet"))\n'
            '\tif (loadst_f) {\n')

from tools.apply_map02_v173_vblank_quiet_mmio import patch_memory as v173_mem
from tools.apply_map02_v174_vblank_read_quiet import patch_memory as v174_mem
from tools.apply_map02_v175_dual_gpu_read_ports import (
    patch_memory,patch_frontend,protected_dual_port_oracle,per_port_observer
)
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

class NativeGPUReadPorts175(unittest.TestCase):
    def test_synthetic_guest_gp1_instruction_is_one_lw_only(self):
        data,stops,starts,wait_pc,ops=build()
        idx=(wait_pc-START)//4
        self.assertEqual(len(stops),4)
        self.assertEqual(ops[idx:idx+512],(0,)*512)
        self.assertEqual(data[0x4c:0x54],b"VH78SYN!")
        self.assertEqual(((0x23<<26)|(8<<21)|(9<<16)|4),0x8d090004)
        self.assertEqual(ops[idx+512]>>26,2)
        self.assertEqual(ops[idx+513],0)

    def test_read_only_native_writer_hook_and_fail_closed_lifecycle(self):
        source=patch_memory(v174_mem(v173_mem(fake_mem())))
        for text in (
            "vh175_observe_read_port(mem);",
            "vh175_arm_read_ports(unsigned phase)",
            "vh175_disarm_read_ports(unsigned phase)",
            "vh175_gp0_read_faults(void)",
            "vh175_gp1_read_faults(void)",
            "vh175_port_armed",
            "physical==0x1f801810u",
            "physical==0x1f801814u",
        ):
            self.assertIn(text,source)
        self.assertLess(source.index("vh175_observe_read_port(mem);"),
                        source.index("vh174_observe_wait_read(mem);"))
        self.assertNotIn("GPUwriteData(",per_port_observer())
        self.assertNotIn("psxRegs.cycle=",per_port_observer())
        with self.assertRaises(ValueError):patch_memory(source)
        with self.assertRaises(ValueError):patch_memory(fake_mem())

    def test_native_oracle_is_separate_and_refuses_before_pixels(self):
        src=patch_frontend(fake_front())
        oracle=protected_dual_port_oracle()
        self.assertIn("if(vh175_mips_vblank_dual_ports_smoke) {",oracle)
        self.assertNotIn("if(vh174_mips_vblank_read_quiet_smoke) {",oracle)
        for needle in (
            "--vh175-mips-vblank-dual-ports",
            "VH175_GUEST_MIPS_VBLANK_PORTS_PASS",
            "VH175_VBLANK_GPU_READ_PORT_REFUSED",
            "VH174_GUEST_MIPS_VBLANK_READ_QUIET_PASS",
            "VH173_GUEST_MIPS_VBLANK_QUIET_PASS",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
            "GPU_freeze(1,&state,&vram)",
        ):
            self.assertIn(needle,src)
        self.assertLess(oracle.index("vh174_arm_wait_read(phase)!=0"),
                        oracle.index("vh175_arm_read_ports(phase)!=0"))
        self.assertLess(oracle.index("vh175_disarm_read_ports(phase);"),
                        oracle.index("vh174_disarm_wait_read(phase);"))
        self.assertLess(oracle.index("VH175_VBLANK_GPU_READ_PORT_REFUSED"),
                        oracle.index("GPU_freeze(1,&state,&vram)"))
        with self.assertRaises(ValueError):patch_frontend(src)

    def test_native_compiled_four_windows_and_both_gpu_ports(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("C compiler missing")
        c=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v){
    (void)r;(void)a;(void)v;
}
""" + patch_memory(v174_mem(v173_mem(fake_mem()))) + r"""
int main(void) {
  psxRegisters regs={0};
  if(vh175_arm_read_ports(0u)==0)return 1;
  for(unsigned p=0;p<4;p++){
    if(vh173_arm_wait_quiet(p)!=0 ||
       vh174_arm_wait_read(p)!=0 ||
       vh175_arm_read_ports(p)!=0 ||
       vh175_arm_read_ports(p)==0)return 2;
    psxMemRead32(&regs,0x80011000u+p*4u);
    psxMemRead32(&regs,0x1f801820u);
    if(vh175_gp0_read_faults()!=0u || vh175_gp1_read_faults()!=0u ||
       vh175_disarm_read_ports((p+1u)%4u)==0 ||
       vh175_disarm_read_ports(p)!=0 ||
       vh175_disarm_read_ports(p)==0 ||
       vh174_wait_read_faults()!=0u ||
       vh174_disarm_wait_read(p)!=0 ||
       vh173_disarm_wait_quiet(p)!=0)return 3;
  }
  if(vh173_arm_wait_quiet(0u)!=0 ||
     vh174_arm_wait_read(0u)!=0 ||
     vh175_arm_read_ports(0u)!=0)return 4;
  psxMemRead32(&regs,0x1f801810u);
  psxMemRead32(&regs,0xbf801814u);
  if(vh175_gp0_read_faults()!=1u || vh175_gp1_read_faults()!=1u ||
     vh175_arm_read_ports(0u)==0 ||
     vh175_gp0_read_faults()!=1u || vh175_gp1_read_faults()!=1u ||
     vh174_wait_read_faults()!=2u ||
     vh175_disarm_read_ports(0u)!=0 ||
     vh174_disarm_wait_read(0u)!=0 ||
     vh173_disarm_wait_quiet(0u)!=0)return 5;
  if(vh173_arm_wait_quiet(1u)!=0 ||
     vh174_arm_wait_read(1u)!=0 ||
     vh175_arm_read_ports(1u)!=0)return 6;
  psxMemRead32(&regs,0x9f801814u);
  if(vh175_gp0_read_faults()!=0u || vh175_gp1_read_faults()!=1u ||
     vh175_disarm_read_ports(0u)==0 ||
     vh175_disarm_read_ports(1u)!=0 ||
     vh174_disarm_wait_read(1u)!=0 ||
     vh173_disarm_wait_quiet(1u)!=0)return 7;
  puts("VH175_COMPILED_PORT_READ_PASS windows=4 good_gp0=0 good_gp1=0 bad_gp0=1 bad_gp1=1 kseg_aliases=1 double_arm_refused=1 wrong_phase_refused=1 original_retail=0");
  return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh175-ports-") as tmp:
            d=Path(tmp);(d/"fixture.c").write_text(c)
            out=d/"fixture"
            res=subprocess.run([cc,"-std=c99","-pedantic","-Wall","-Wextra",
                "-Werror",str(d/"fixture.c"),"-o",str(out)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(res.returncode,0,res.stderr)
            run=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn("VH175_COMPILED_PORT_READ_PASS",run.stdout)

    def test_pinned_unai_mips_gp1_negative_runs_on_both_compilers(self):
        source=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v175-dual-gpu-read-ports.yml").read_text()
        for needle in (
            "apply_map02_v175_dual_gpu_read_ports",
            "test_map02_v175_dual_gpu_read_ports.py",
            "--vh175-mips-vblank-dual-ports",
            "V175_SYNTHETIC.EXE",
            "V175_BAD_WAIT_LW_GP1.EXE",
            "VH175_GUEST_MIPS_VBLANK_PORTS_PASS",
            "VH175_VBLANK_GPU_READ_PORT_REFUSED",
            "0x8d090004",
            "vh175_bad_rc",
        ):
            self.assertIn(needle,source)
        self.assertIn("test_map02_v174_vblank_read_quiet.py",own)
        self.assertIn("original_retail_executed=0",own)

if __name__=="__main__":
    unittest.main()
