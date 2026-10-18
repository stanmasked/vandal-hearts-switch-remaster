#!/usr/bin/env python3
"""v169: source-authored indexed STP/ABR and vertical E2 MIPS-to-VRAM proofs."""
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
from tools.apply_map02_v169_mips_stp_e2v_vram import (
    expected_stp_source,patch_memory,patch_frontend,native_mmio_c
)
from tools.make_map02_v75_indexed_stp_e2v_exe import (
    build,GP0_SEQUENCE,REGIONS,E2_VERTICAL,expected_pixel,
    PALETTE4,PALETTE8
)
from tools.make_map02_v70_synthetic_psx_exe import START,sw

def stub_memory():
    return """void vh140_mmio_enable(unsigned mutate_expected) {\n (void)mutate_expected;\n}
void psxMemWrite32(psxRegisters *regs,u32 mem,u32 value){
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
}
"""

def stub_frontend():
    return ('\tint vh168_clut_uv_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh168-mips-clut-uv-vram"))\n'
            '\tif (loadst_f) {\n')

class MipsIndexedStpE2V169(unittest.TestCase):
    def test_236_mips_source_pcs_ft4_abr_stp_and_e2_vertical_packets(self):
        gp1,pcs,words,ft4s,end=expected_stp_source()
        image,real_end,program=build()
        self.assertEqual(end,real_end)
        self.assertEqual(len(image),6144)
        self.assertEqual(len(words),236)
        self.assertEqual(tuple(words),GP0_SEQUENCE)
        self.assertEqual(len(set(pcs)),236)
        self.assertEqual(ft4s,(189,198,207,216,226))
        self.assertEqual([words[k] for k in ft4s],
                         [0x2f000000]*4+[0x2d000000])
        self.assertEqual(gp1,START+4*4)
        self.assertEqual(program[4],sw(9,0,8))
        for i,pc in enumerate(pcs):
            self.assertEqual(pc,START+4*(8+3*i))
            self.assertEqual(program[(pc-START)//4],sw(9,0,8))
        self.assertEqual(sum(i==sw(9,0,8) for i in program),237)
        self.assertEqual(words.count(0xa0000000),4)
        self.assertEqual(words[225],E2_VERTICAL)
        self.assertEqual(E2_VERTICAL,0xe2008020)
        self.assertEqual(words[235],0xe2000000)
        self.assertEqual((words[211]>>16,words[220]>>16),(0x0a1,0x081))

    def test_exact_five_region_stp_abr_and_independent_511_pixels(self):
        self.assertEqual(REGIONS,(
            ("clut4_stp_abr0",40,0xbc0f),
            ("clut4_nonstp",56,0x03e0),
            ("clut8_stp_abr1",72,0xfc1f),
            ("clut8_transparent",88,0x7c00),
            ("e2_vertical_v8",104,0x03ff),
        ))
        self.assertEqual(PALETTE4[1],0x801f)
        self.assertEqual(PALETTE8[17],0x801f)
        image=[expected_pixel(x,y) for y in range(103,110) for x in range(39,112)]
        self.assertEqual(len(image),511)
        self.assertEqual(sum(x!=0 for x in image),80)
        self.assertEqual(image.count(0),431)
        for title,left,value in REGIONS:
            self.assertEqual(
                [expected_pixel(x,104) for x in range(left,left+4)],
                [value]*4)

    def test_read_only_true_mmio_hook_and_vram_after_source_proof(self):
        mem=patch_memory(stub_memory())
        for token in ("vh169_expected_pc[]","vh169_expected_word[]",
                      "vh169_note_stp_e2v_mips_sw(regs,mem,value)",
                      "regs->pc!=vh169_expected_pc[vh169_seen]+4u",
                      "val!=vh169_expected_word[vh169_seen]"):
            self.assertIn(token,mem)
        self.assertLess(mem.index("if(vh169_active) vh169_note_stp_e2v_mips_sw"),
                        mem.index("vh138_pc_observe(regs,mem,value);"))
        with self.assertRaises(ValueError):patch_memory(mem)
        with self.assertRaises(ValueError):
            patch_memory(stub_memory().replace(
                "vh138_pc_observe(regs,mem,value);",
                "vh138_pc_observe(regs,mem,0);"))
        front=patch_frontend(stub_frontend())
        for marker in (
            "--vh169-mips-stp-e2v-vram","vh169_arm_stp_e2v_origin()!=0",
            "vh169_disarm_stp_e2v_origin();","seen!=236u",
            "gp1_count!=1u || faults!=0u",
            "VH169_STP_E2V_MIPS_GP0_REFUSED",
            "VH169_GUEST_MIPS_STP_E2V_VRAM_PASS",
            "VH75_VRAM_PASS checked=511","checked!=511 || wrong",
            "vram[y*1024+x]!=expected","VH75_EXE_REFUSED"
        ):
            self.assertIn(marker,front)
        self.assertLess(front.index("vh169_arm_stp_e2v_origin()!=0"),
                        front.index("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"))
        self.assertLess(front.index("vh169_disarm_stp_e2v_origin();"),
                        front.index("GPU_freeze(1,&state,&vram)"))
        self.assertLess(front.index("if(checked!=511 || wrong)"),
                        front.index("VH169_GUEST_MIPS_STP_E2V_VRAM_PASS"))
        with self.assertRaises(ValueError):patch_frontend(front)

    def test_compiled_236_gpu_word_mmio_origin_and_negative_cases(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("compiler unavailable")
        c=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 addr,u32 v){
    (void)r;(void)addr;(void)v;
}
""" + patch_memory(stub_memory()) + r"""
int main(void){
    psxRegisters cpu={0};
    cpu.code=0xad090000u;
    if(vh169_arm_stp_e2v_origin()!=0 || vh169_arm_stp_e2v_origin()==0)
        return 1;
    cpu.pc=VH169_GP1_PC_PLUS4;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    for(unsigned i=0;i<VH169_GP0_LENGTH;i++){
        cpu.pc=vh169_expected_pc[i]+4u;
        psxMemWrite32(&cpu,0x1f801810u,vh169_expected_word[i]);
    }
    psxMemWrite32(&cpu,0x80011000u,0x70000001u);
    if(vh169_stp_e2v_gp0_seen()!=236u || vh169_stp_e2v_gp1_seen()!=1u ||
       vh169_stp_e2v_faults()!=0u || vh169_disarm_stp_e2v_origin()!=0)
        return 2;
    if(vh169_disarm_stp_e2v_origin()==0)return 3;
    if(vh169_arm_stp_e2v_origin()!=0)return 4;
    cpu.pc=vh169_expected_pc[0]+4u;
    psxMemWrite32(&cpu,0x1f801810u,vh169_expected_word[0]);
    if(vh169_stp_e2v_gp0_seen()!=0u || vh169_stp_e2v_faults()!=1u)
        return 5;
    if(vh169_disarm_stp_e2v_origin()!=0)return 6;
    if(vh169_arm_stp_e2v_origin()!=0)return 7;
    cpu.pc=VH169_GP1_PC_PLUS4;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    cpu.pc=vh169_expected_pc[0]+8u;
    psxMemWrite32(&cpu,0x1f801810u,vh169_expected_word[0]);
    cpu.pc=vh169_expected_pc[0]+4u;
    cpu.code=0u;
    psxMemWrite32(&cpu,0x1f801810u,vh169_expected_word[0]);
    cpu.code=0xad090000u;
    psxMemWrite32(&cpu,0x1f801810u,vh169_expected_word[0]^1u);
    if(vh169_stp_e2v_gp0_seen()!=0u || vh169_stp_e2v_faults()!=3u)
        return 8;
    if(vh169_disarm_stp_e2v_origin()!=0)return 9;
    if(vh169_arm_stp_e2v_origin()!=0)return 10;
    cpu.pc=VH169_GP1_PC_PLUS4;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    for(unsigned i=0;i<VH169_GP0_LENGTH;i++){
        cpu.pc=vh169_expected_pc[i]+4u;
        psxMemWrite32(&cpu,0x1f801810u,vh169_expected_word[i]);
    }
    psxMemWrite32(&cpu,0x1f801810u,0xe2008020u);
    if(vh169_stp_e2v_gp0_seen()!=236u || vh169_stp_e2v_faults()!=1u)
        return 11;
    if(vh169_disarm_stp_e2v_origin()!=0)return 12;
    puts("VH169_COMPILED_STP_E2V_MIPS_PROOF_PASS gp0_words=236 gp1=1 ft4=5 a0_uploads=4 missing_gp1_refused=1 wrong_pc_refused=1 wrong_opcode_refused=1 wrong_word_refused=1 extra_refused=1 original_retail=0");
    return 0;
}
""".replace("VH169_GP1_PC_PLUS4",f"0x{expected_stp_source()[0]+4:08x}u")
        with tempfile.TemporaryDirectory(prefix="vh169-stp-e2v-") as td:
            base=Path(td)
            (base/"test.c").write_text(c)
            exe=base/"test"
            build_result=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(base/"test.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(build_result.returncode,0,build_result.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn("VH169_COMPILED_STP_E2V_MIPS_PROOF_PASS",run.stdout)

    def test_full_pinned_native_and_e2_vertical_instruction_mutation(self):
        w=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v169-mips-stp-e2v-vram.yml").read_text()
        for mark in (
            "apply_map02_v169_mips_stp_e2v_vram",
            "test_map02_v169_mips_stp_e2v_vram.py",
            "--vh169-mips-stp-e2v-vram",
            "V169_SYNTHETIC.EXE","V169_BAD_E2V.EXE",
            "VH169_GUEST_MIPS_STP_E2V_VRAM_PASS",
            "VH169_STP_E2V_MIPS_GP0_REFUSED",
            "VH75_VRAM_PASS checked=511",
        ):
            self.assertIn(mark,w)
        self.assertIn("test_map02_v168_mips_clut_uv_vram.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
