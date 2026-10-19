#!/usr/bin/env python3
"""v177: expose every GP0/GP1 8-bit and aligned 16-bit lane to native tests.

Complements four green genuine MIPS v176 mutations with four untouched lane
and port combinations. Tests synthetic programs, not retail MAP02.
"""
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
from tools.apply_map02_v176_narrow_gpu_mmio import patch_memory as v176_mem
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

MUTATIONS={
    "LB_GP0_HI":(0x81090003,0,0,0), # LB t1,3(t0)
    "LH_GP1_HI":(0x85090006,1,0,1), # LH t1,6(t0), aligned +2 of GP1
    "SB_GP0_HI":(0xa1090003,0,1,0), # SB t1,3(t0)
    "SH_GP1_HI":(0xa5090006,1,1,1), # SH t1,6(t0), aligned +2 of GP1
}

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
void psxMemWrite8(psxRegisters *regs, u32 mem, u32 value) {
 (void)regs;(void)mem;(void)value;
}
void psxMemWrite16(psxRegisters *regs, u32 mem, u32 value) {
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

def observed_mem():
    return v176_mem(v175_mem(v174_mem(v173_mem(fake_mem()))))

class V177FullGPURegisterLaneWitness(unittest.TestCase):
    def test_single_word_synthetic_nop_mutations_are_aligned_and_cover_missing_ports(self):
        data,stops,starts,pc,ops=build()
        idx=(pc-START)//4
        self.assertEqual(len(stops),4)
        self.assertEqual(data[0x4c:0x54],b"VH78SYN!")
        self.assertEqual(ops[idx:idx+512],(0,)*512)
        for tag,(ins,width,direction,port) in MUTATIONS.items():
            self.assertEqual(ins>>26,0x20 if tag.startswith("LB") else
                             0x21 if tag.startswith("LH") else
                             0x28 if tag.startswith("SB") else 0x29)
            self.assertEqual((ins>>21)&31,8)
            self.assertEqual((ins>>16)&31,9)
            offset=ins&0xffff
            self.assertEqual(port,(offset>>2))
            if width==1:self.assertEqual(offset%2,0)
            if tag.endswith("HI"):self.assertEqual(offset&3,3 if width==0 else 2)
            self.assertIn(direction,(0,1))

    def test_existing_v176_observer_covers_all_gpu_register_bytes_and_halfwords(self):
        source=observed_mem()
        for text in (
            "physical<0x1f801810u",
            "physical>0x1f801817u",
            "port=(physical-0x1f801810u)>>2",
            "vh176_hits[width][writing][port]++",
            "vh176_observe_narrow(mem,0u,0u)",
            "vh176_observe_narrow(mem,1u,1u)",
        ):self.assertIn(text,source)
        self.assertNotIn("psxRegs.cycle=",source[source.index("/* v176: read-only witness"):source.index("unsigned vh173_wait_mmio_faults")])

    def test_compiled_real_accessors_cover_all_24_gp0_gp1_byte_and_halfword_lanes(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("C compiler missing")
        src=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v) {
 (void)r;(void)a;(void)v;
}
""" + observed_mem() + r"""
int main(void) {
    psxRegisters regs={0};
    unsigned p,port,lane;
    if(vh176_arm_narrow(0u)==0)return 1;
    for(p=0;p<4u;p++){
        if(vh173_arm_wait_quiet(p)!=0 ||
           vh174_arm_wait_read(p)!=0 ||
           vh175_arm_read_ports(p)!=0 ||
           vh176_arm_narrow(p)!=0)return 2;
        psxMemRead8(&regs,0x1f80180fu);
        psxMemRead16(&regs,0x1f801818u);
        psxMemWrite8(&regs,0x1f801818u,0u);
        psxMemWrite16(&regs,0x1f80180eu,0u);
        if(vh176_narrow_total()!=0u ||
           vh176_disarm_narrow(p)!=0 ||
           vh175_disarm_read_ports(p)!=0 ||
           vh174_disarm_wait_read(p)!=0 ||
           vh173_disarm_wait_quiet(p)!=0)return 3;
    }
    if(vh173_arm_wait_quiet(0u)!=0 ||
       vh174_arm_wait_read(0u)!=0 ||
       vh175_arm_read_ports(0u)!=0 ||
       vh176_arm_narrow(0u)!=0)return 4;
    for(port=0;port<2u;port++){
        u32 base=0x1f801810u+port*4u;
        for(lane=0;lane<4u;lane++){
            u32 addr=base+lane;
            if(lane%2u==0u)addr|=0xa0000000u;
            psxMemRead8(&regs,addr);
            psxMemWrite8(&regs,addr,0u);
            if(lane%2u==0u) {
                psxMemRead16(&regs,addr);
                psxMemWrite16(&regs,addr,0u);
            }
        }
    }
    if(vh176_narrow_total()!=24u ||
       vh175_gp0_read_faults()!=0u ||
       vh175_gp1_read_faults()!=0u ||
       vh174_wait_read_faults()!=0u ||
       vh173_wait_mmio_faults()!=0u)return 5;
    for(port=0;port<2u;port++){
        if(vh176_narrow_count(0u,0u,port)!=4u ||
           vh176_narrow_count(0u,1u,port)!=4u ||
           vh176_narrow_count(1u,0u,port)!=2u ||
           vh176_narrow_count(1u,1u,port)!=2u)return 6;
    }
    if(vh176_arm_narrow(0u)==0 || vh176_narrow_total()!=24u ||
       vh176_disarm_narrow(1u)==0 ||
       vh176_disarm_narrow(0u)!=0 ||
       vh175_disarm_read_ports(0u)!=0 ||
       vh174_disarm_wait_read(0u)!=0 ||
       vh173_disarm_wait_quiet(0u)!=0)return 7;
    puts("VH177_COMPILED_ALL_NARROW_LANES_PASS windows=4 gpu_ports=2 byte_lanes=16 halfword_lanes=8 total=24 alias_checked=1 adjacent_not_counted=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh177-gpu-lanes-") as d:
            f=Path(d)/"fixture.c";exe=Path(d)/"fixture"
            f.write_text(src)
            proc=subprocess.run([cc,"-std=c99","-pedantic","-Wall","-Wextra",
                "-Werror",str(f),"-o",str(exe)],capture_output=True,text=True,timeout=35)
            self.assertEqual(proc.returncode,0,proc.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn("VH177_COMPILED_ALL_NARROW_LANES_PASS",run.stdout)

    def test_native_workflow_has_four_exact_lane_mutants_and_real_pcsx_refusals(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v177-narrow-gpu-lanes.yml").read_text()
        for needle in (
            "test_map02_v177_narrow_gpu_lanes.py",
            "--vh176-mips-vblank-narrow-mmio",
            "V177_SYNTHETIC.EXE",
            "V177_BAD_",
            "VH176_NARROW_MMIO_REFUSED",
            "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
            "0x81090003",
            "0x85090006",
            "0xa1090003",
            "0xa5090006",
            'test "$rc" -eq 82',
            "LH_GP1_HI",
            "SH_GP1_HI",
        ):self.assertIn(needle,workflow)
        self.assertIn("test_map02_v176_narrow_gpu_mmio.py",own)
        self.assertIn("original_retail_executed=0",own)

if __name__=="__main__":
    unittest.main()
