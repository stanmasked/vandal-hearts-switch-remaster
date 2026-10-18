#!/usr/bin/env python3
"""v166 guest MIPS store-PC -> native GP0 words -> raster stage checks."""
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
from tools.apply_map02_v165_guest_gp0_pixel_binding import patch_frontend as patch_v165
from tools.apply_map02_v166_mips_pc_gp0_vram import (
    patch_frontend,patch_memory,source_pc_triplets,mmio_pc_witness_c
)
from tools.make_map02_v121_mips_gp0_return_exe import (
    build,stage_body,sw,COLORS,RECT_XY,RECT_SIZE
)


def fake_memory():
    return """void vh140_mmio_enable(unsigned mutate_expected) {
    (void)mutate_expected;
}
void psxMemWrite32(psxRegisters *regs, u32 mem, u32 value) {
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
}
"""


class MipsPcGp0Vram166(unittest.TestCase):
    def test_source_generated_nonoverlapping_15_real_guest_sw_pcs(self):
        pcs=source_pc_triplets()
        _, stops,ops,starts=build()
        self.assertEqual(len(pcs),5)
        self.assertEqual(len(set(p for row in pcs for p in row)),15)
        for i,row in enumerate(pcs):
            stage=i+1
            self.assertEqual(row,tuple(starts[stage]+4*j for j in (4,7,10)))
            self.assertEqual(tuple(ops[(starts[stage]-starts[0])//4+j]
                             for j in (4,7,10)),(sw(9,0,8),)*3)
        self.assertIn("regs->pc!=vh166_expected_pc[vh166_stage][vh166_count]+4u",
                      mmio_pc_witness_c())
        self.assertIn("regs->code!=0xad090000u",mmio_pc_witness_c())
        self.assertIn("value!=vh166_expected_words[vh166_stage][vh166_count]",
                      mmio_pc_witness_c())

    def test_source_anchor_exact_and_no_duplicate_patching(self):
        patched=patch_memory(fake_memory())
        self.assertLess(patched.index("vh166_observe_guest_sw_pc(regs,mem,value)"),
                        patched.index("vh138_pc_observe(regs,mem,value);"))
        self.assertIn("if(vh166_active)",patched)
        self.assertIn("if(physical!=0x1f801810u)",patched)
        self.assertIn("if((physical&0xfffffff8u)==0x1f801810u)",patched)
        self.assertEqual(patched.count("vh166_expected_pc[5][3]"),1)
        with self.assertRaises(ValueError):
            patch_memory(patched)
        with self.assertRaises(ValueError):
            patch_memory(fake_memory().replace("vh138_pc_observe(regs,mem,value);",
                                                "vh138_pc_observe(regs,mem,0);"))

    def test_frontend_blocks_false_pc_provenance_before_vram(self):
        base="\textern int vh161_disarm_gpu_queue(void);\n"+frontend_fixture()
        patched=patch_frontend(patch_v165(patch_v164(base)))
        for mark in (
            "--vh166-mips-pc-gp0-vram-chain",
            "vh166_mips_pc_gp0_vram_chain=1;",
            "vh166_arm_guest_sw_pc(phase)",
            "vh166_guest_sw_pc_count();",
            "vh166_guest_sw_pc_faults();",
            "vh166_disarm_guest_sw_pc();",
            "VH166_GUEST_SW_PC_REFUSED",
            "VH166_GUEST_MIPS_PC_GP0_VRAM_PASS",
            "phases=5 sw_pcs=15 gp0_words=15 pixels_changed=80",
            "border_unchanged=100 original_retail=0",
            "VH165_GUEST_MIPS_GP0_VRAM_BOUND_PASS",
            "VH164_GUEST_MIPS_UNAI_VRAM_PASS",
        ):
            self.assertIn(mark,patched)
        self.assertLess(patched.index("vh166_arm_guest_sw_pc(phase)"),
                        patched.index("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);",
                                      patched.index("for(unsigned int phase=0;phase<5u;phase++){")))
        self.assertLess(patched.index("unsigned pc_count=vh166_guest_sw_pc_count();"),
                        patched.index("GPUFreeze_t freeze_state={0};"))
        with self.assertRaises(ValueError):
            patch_frontend(patched)

    def test_compiled_true_memory_write_observer_with_mutated_sw_pc_and_word(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("compiler unavailable")
        c=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *regs,u32 address,u32 value) {
  (void)regs;(void)address;(void)value;
}
""" + patch_memory(fake_memory()) + r"""
int main(void) {
    psxRegisters r={0};
    r.code=0xad090000u;
    for(unsigned stage=0u;stage<5u;stage++) {
        if(vh166_arm_guest_sw_pc(stage)!=0 ||
           vh166_arm_guest_sw_pc(stage)==0) return 1;
        for(unsigned idx=0u;idx<3u;idx++){
            r.pc=vh166_expected_pc[stage][idx]+4u;
            psxMemWrite32(&r,0x1f801810u,
                          vh166_expected_words[stage][idx]);
        }
        /* Each guest MIPS stage also stores a CPU RAM stage marker.
         * This is not another GPU packet and must not cause a fault. */
        psxMemWrite32(&r,0x80011100u+stage*4u,0x12100000u+stage);
        if(vh166_guest_sw_pc_count()!=3u ||
           vh166_guest_sw_pc_faults()) return 2;
        if(vh166_disarm_guest_sw_pc()!=0 ||
           vh166_disarm_guest_sw_pc()==0) return 3;
    }
    if(vh166_arm_guest_sw_pc(5u)==0) return 4;
    if(vh166_arm_guest_sw_pc(0u)!=0) return 5;
    r.pc=vh166_expected_pc[0][0]+8u;
    psxMemWrite32(&r,0x1f801810u,vh166_expected_words[0][0]);
    r.pc=vh166_expected_pc[0][0]+4u;
    r.code=0u;
    psxMemWrite32(&r,0x1f801810u,vh166_expected_words[0][0]);
    r.code=0xad090000u;
    psxMemWrite32(&r,0x1f801814u,vh166_expected_words[0][0]);
    psxMemWrite32(&r,0x1f801810u,0xbad00000u);
    if(vh166_guest_sw_pc_count()!=0u ||
       vh166_guest_sw_pc_faults()!=4u) return 6;
    if(vh166_disarm_guest_sw_pc()!=0) return 7;
    if(vh166_arm_guest_sw_pc(1u)!=0) return 8;
    r.pc=vh166_expected_pc[1][0]+4u;
    psxMemWrite32(&r,0x1f801810u,vh166_expected_words[1][0]);
    if(vh166_guest_sw_pc_count()!=1u || vh166_guest_sw_pc_faults())return 9;
    if(vh166_disarm_guest_sw_pc()!=0) return 10;
    if(vh166_guest_sw_pc_count()!=1u) return 11;
    puts("VH166_COMPILED_GUEST_SW_PC_PASS sw_pcs=15 phases=5 bad_pc=refused bad_opcode=refused bad_mmio=refused bad_word=refused missing=refused original_retail=0");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh166-mips-pc-") as td:
            p=Path(td);(p/"m.c").write_text(c)
            output=p/"m"
            built=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(p/"m.c"),"-o",str(output)],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(output)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn("VH166_COMPILED_GUEST_SW_PC_PASS",result.stdout)

    def test_native_gcc_clang_and_mutation_guards_wired(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v166-mips-pc-gp0-vram.yml").read_text()
        for mark in (
            "apply_map02_v166_mips_pc_gp0_vram",
            "test_map02_v166_mips_pc_gp0_vram.py",
            "--vh166-mips-pc-gp0-vram-chain",
            "VH166_GUEST_MIPS_PC_GP0_VRAM_PASS",
            "VH166_GUEST_SW_PC_REFUSED",
            "VH121_EXE_REFUSED",
        ):
            self.assertIn(mark,workflow)
        self.assertIn("test_map02_v165_guest_gp0_pixel_binding.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
