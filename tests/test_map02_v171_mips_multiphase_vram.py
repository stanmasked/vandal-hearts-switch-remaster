#!/usr/bin/env python3
"""v171 four bounded MIPS ExecuteBlock() calls with real GP0/GP1 MMIO provenance."""
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
from tools.apply_map02_v171_mips_multiphase_vram import (
    expected_phase_source,patch_memory,patch_frontend,mmio_witness_source
)
from tools.make_map02_v77_gpu_multiphase_exe import (
    build,PHASE_GP0,PHASE_GP1,MARKERS,EXPECTED_REGS,X,Y,expected_pixel,
    phase_body
)
from tools.make_map02_v70_synthetic_psx_exe import START,sw


def fake_memory():
    return """void vh140_mmio_enable(unsigned mutate_expected) {
 (void)mutate_expected;
}
void psxMemWrite32(psxRegisters *regs,u32 mem,u32 value){
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
}
"""


def fake_frontend():
    return ('\tint vh170_gpu_state_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh170-mips-ft4-gpu-state"))\n'
            '\tif (loadst_f) {\n')


class GuestMipsFourPhase171(unittest.TestCase):
    def test_exact_72_synthetic_sw_pcs_and_three_gp1_resets(self):
        pcs,gp1,lens,stops=expected_phase_source()
        image,original_stops,ops,starts=build()
        self.assertEqual(stops,original_stops)
        self.assertEqual(len(image),6144)
        self.assertEqual(len(pcs),4)
        self.assertEqual(lens,(49,7,7,9))
        self.assertEqual(sum(lens),72)
        self.assertEqual(len(set(x for phase in pcs for x in phase)),72)
        self.assertEqual(PHASE_GP1,(0x01000000,None,0x01000000,0x00000000))
        self.assertEqual(len([x for x in gp1 if x]),3)
        for phase in range(4):
            self.assertEqual(len(pcs[phase]),lens[phase])
            first=9 if PHASE_GP1[phase] is not None else 4
            self.assertEqual(pcs[phase],tuple(starts[phase]+4*(first+3*i)
                         for i in range(lens[phase])))
            code=phase_body(phase)
            self.assertEqual(code[-1],sw(9,0,10))
            for pc in pcs[phase]:
                self.assertEqual(ops[(pc-START)//4],sw(9,0,8))
        self.assertEqual(EXPECTED_REGS[1],EXPECTED_REGS[2])
        self.assertNotEqual(EXPECTED_REGS[2],EXPECTED_REGS[3])
        self.assertEqual(MARKERS,tuple(0x77010001+i for i in range(4)))

    def test_four_true_vram_readbacks_and_hardware_vblank_not_claimed(self):
        for phase in range(4):
            pixels=[expected_pixel(phase,x,y) for y in range(159,166)
                    for x in range(39,124)]
            self.assertEqual(len(pixels),595)
            self.assertEqual(pixels.count(0),499)
            self.assertEqual(sum(v!=0 for v in pixels),96)
        self.assertEqual(4*595,2380)
        self.assertIn("A block boundary is NOT VBlank",
                      (ROOT/"tools/apply_map02_v171_mips_multiphase_vram.py").read_text())

    def test_actual_psxmem_observer_then_each_native_pixel_readback(self):
        mem=patch_memory(fake_memory())
        for token in (
            "vh171_gp0_pc[4][49]","vh171_gp0_words[4][49]",
            "vh171_gp1_pc[4]","vh171_gp1_words[4]",
            "vh171_note_phase_mips_mmio(regs,mem,value)",
            "regs->pc!=vh171_gp0_pc[vh171_stage][vh171_seen]+4u",
            "value!=vh171_gp0_words[vh171_stage][vh171_seen]",
        ):
            self.assertIn(token,mem)
        self.assertLess(mem.index("if(vh171_active) vh171_note_phase_mips_mmio"),
                        mem.index("vh138_pc_observe(regs,mem,value);"))
        with self.assertRaises(ValueError):patch_memory(mem)
        with self.assertRaises(ValueError):
            patch_memory(fake_memory().replace(
                "vh138_pc_observe(regs,mem,value);",
                "vh138_pc_observe(regs,mem,0);"))
        main=patch_frontend(fake_frontend())
        for text in (
            "--vh171-mips-multiphase-vram",
            "vh171_arm_guest_phase(phase)!=0",
            "vh171_disarm_guest_phase();",
            "VH171_PHASE_GPU_ORIGIN_REFUSED",
            "vh171_gp0!=vh171_expected_gp0[phase]",
            "vh171_gp1!=vh171_expected_gp1[phase]",
            "VH171_GUEST_MIPS_MULTIPHASE_VRAM_PASS",
            "gp0_words=72 gp1_writes=3 samples=2380",
            "vblank_asserted=0 original_retail=0",
            "VH77_PHASE_PASS phase=%u checked=595 guard=499",
            "VH77_MULTIPHASE_PASS phases=4 samples=2380",
            "GPU_freeze(1,&state,&vram)",
            "vram[y*1024+x]!=expected",
            "VH77_EXE_REFUSED",
        ):
            self.assertIn(text,main)
        self.assertEqual(main.count("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"),1)
        self.assertLess(main.index("vh171_arm_guest_phase(phase)!=0"),
                        main.index("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"))
        self.assertLess(main.index("vh171_disarm_guest_phase();"),
                        main.index("GPU_freeze(1,&state,&vram)"))
        self.assertLess(main.index("VH77_GPU_STATE_REFUSED count=%u"),
                        main.index("VH171_GUEST_MIPS_MULTIPHASE_VRAM_PASS"))
        with self.assertRaises(ValueError):patch_frontend(main)

    def test_compiled_four_phase_actual_mmio_positive_and_bad_gp1(self):
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
""" + patch_memory(fake_memory()) + r"""
int main(void) {
    psxRegisters cpu={0};
    cpu.code=0xad090000u;
    unsigned total0=0,total1=0;
    for(unsigned phase=0u;phase<4u;phase++){
        if(vh171_arm_guest_phase(phase)!=0 ||
           vh171_arm_guest_phase(phase)==0)return 1;
        if(vh171_gp1_pc[phase]) {
            cpu.pc=vh171_gp1_pc[phase]+4u;
            psxMemWrite32(&cpu,0x1f801814u,vh171_gp1_words[phase]);
        }
        for(unsigned i=0;i<vh171_gp0_lengths[phase];i++){
            cpu.pc=vh171_gp0_pc[phase][i]+4u;
            psxMemWrite32(&cpu,0x1f801810u,vh171_gp0_words[phase][i]);
        }
        psxMemWrite32(&cpu,0x80011000u+phase*4u,0x77010001u+phase);
        if(vh171_guest_phase_gp0_words()!=vh171_gp0_lengths[phase] ||
           vh171_guest_phase_gp1_writes()!=(vh171_gp1_pc[phase]?1u:0u) ||
           vh171_guest_phase_faults()!=0u ||
           vh171_disarm_guest_phase()!=0)return 2;
        total0+=vh171_gp0_lengths[phase];
        total1+=vh171_gp1_pc[phase]?1u:0u;
    }
    if(total0!=72u || total1!=3u ||
       vh171_disarm_guest_phase()==0)return 3;
    if(vh171_arm_guest_phase(4u)==0)return 4;
    /* Wrong guest GP1 word during FIFO-reset phase is refused. */
    if(vh171_arm_guest_phase(2u)!=0)return 5;
    cpu.pc=vh171_gp1_pc[2]+4u;
    psxMemWrite32(&cpu,0x1f801814u,0x00000000u);
    if(vh171_guest_phase_gp1_writes()!=0u ||
       vh171_guest_phase_faults()!=1u)return 6;
    if(vh171_disarm_guest_phase()!=0)return 7;
    /* Phase without GP1 refuses unexpected GP1. */
    if(vh171_arm_guest_phase(1u)!=0)return 8;
    cpu.pc=vh171_gp0_pc[1][0]+4u;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    if(vh171_guest_phase_faults()!=1u)return 9;
    if(vh171_disarm_guest_phase()!=0)return 10;
    /* GP0 submitted before mandatory GP1, PC/opcode/value mismatches. */
    if(vh171_arm_guest_phase(0u)!=0)return 11;
    cpu.pc=vh171_gp0_pc[0][0]+4u;
    psxMemWrite32(&cpu,0x1f801810u,vh171_gp0_words[0][0]);
    cpu.pc=vh171_gp1_pc[0]+4u;
    psxMemWrite32(&cpu,0x1f801814u,vh171_gp1_words[0]);
    cpu.pc=vh171_gp0_pc[0][0]+8u;
    psxMemWrite32(&cpu,0x1f801810u,vh171_gp0_words[0][0]);
    cpu.pc=vh171_gp0_pc[0][0]+4u;
    cpu.code=0u;
    psxMemWrite32(&cpu,0x1f801810u,vh171_gp0_words[0][0]);
    cpu.code=0xad090000u;
    psxMemWrite32(&cpu,0x1f801810u,vh171_gp0_words[0][0]^1u);
    if(vh171_guest_phase_gp0_words()!=0u ||
       vh171_guest_phase_faults()!=4u)return 12;
    if(vh171_disarm_guest_phase()!=0)return 13;
    puts("VH171_COMPILED_GUEST_MULTIPHASE_PASS phases=4 gp0_words=72 gp1_writes=3 wrong_gp1_refused=1 no_gp1_phase_refused=1 early_gp0_refused=1 bad_pc_refused=1 bad_opcode_refused=1 bad_word_refused=1 original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh171-guest-multiphase-") as td:
            d=Path(td);(d/"fixture.c").write_text(c);exe=d/"fixture"
            comp=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(d/"fixture.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=40)
            self.assertEqual(comp.returncode,0,comp.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn("VH171_COMPILED_GUEST_MULTIPHASE_PASS",run.stdout)

    def test_pinned_native_gcc_clang_and_source_gp1_mutation_wired(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v171-mips-multiphase-vram.yml").read_text()
        for mark in (
            "apply_map02_v171_mips_multiphase_vram",
            "test_map02_v171_mips_multiphase_vram.py",
            "--vh171-mips-multiphase-vram",
            "V171_SYNTHETIC.EXE","V171_BAD_GP1.EXE",
            "VH171_GUEST_MIPS_MULTIPHASE_VRAM_PASS",
            "VH171_PHASE_GPU_ORIGIN_REFUSED",
            "VH77_MULTIPHASE_PASS phases=4 samples=2380",
        ):
            self.assertIn(mark,native)
        self.assertIn("test_map02_v170_mips_ft4_gpu_state.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
