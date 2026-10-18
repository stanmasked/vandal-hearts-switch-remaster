#!/usr/bin/env python3
"""v168 source-bound indexed 4bpp/8bpp CLUT UV/TPage/E2 to real Unai VRAM."""
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
from tools.apply_map02_v168_mips_clut_uv_vram import (
    expected_clut_source,native_mmio_source,patch_memory,patch_frontend,
)
from tools.make_map02_v74_indexed_clut_exe import (
    GP0_SEQUENCE,build,PALETTE4,PALETTE8,EXPECTED4,EXPECTED8,
    EXPECTED_WINDOW,EXPECTED_TRANSPARENT,expected_pixel,
)
from tools.make_map02_v70_synthetic_psx_exe import START,sw


def stub_memory():
    return """void vh140_mmio_enable(unsigned mutate_expected) {
 (void)mutate_expected;
}
void psxMemWrite32(psxRegisters *regs,u32 mem,u32 value) {
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
}
"""


def stub_frontend():
    return ('\tint vh167_ft4_mips_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh167-mips-ft4-texture-vram"))\n'
            '\tif (loadst_f) {\n')


class MipsIndexedClutUV168(unittest.TestCase):
    def test_211_guest_gp0_words_actual_mips_sw_pcs_and_indexed_ft4(self):
        gp1,pcs,words,starts,end=expected_clut_source()
        image,pc,ops=build()
        self.assertEqual(pc,end)
        self.assertEqual(len(image),6144)
        self.assertEqual(len(words),211)
        self.assertEqual(words,GP0_SEQUENCE)
        self.assertEqual(len(set(pcs)),211)
        self.assertEqual(starts,(170,179,189,202))
        self.assertEqual(ops[4],sw(9,0,8))
        self.assertEqual(gp1,START+16)
        for i,addr in enumerate(pcs):
            self.assertEqual(addr,START+4*(8+3*i))
            self.assertEqual(ops[(addr-START)//4],sw(9,0,8))
        self.assertEqual(sum(op==sw(9,0,8) for op in ops),212)
        self.assertEqual(words.count(0xa0000000),4)
        self.assertEqual((words[172]>>16,words[181]>>16),(32,33))
        self.assertEqual((words[174]>>16,words[183]>>16),(0,0x081))
        self.assertEqual(words[188],0xe2000401)
        self.assertEqual(words[198],0xe2000000)

    def test_indexed_palette_uv_and_399_exact_readback_pixel_expectations(self):
        self.assertEqual(EXPECTED4,(0x001f,0x03e0,0x7c00,0x7fff))
        self.assertEqual(EXPECTED8,(0x4210,0x7c1f,0x7fe0,0x03ff))
        self.assertEqual(EXPECTED_WINDOW,(0x03ff,0x7fe0,0x7c1f,0x4210))
        self.assertEqual(EXPECTED_TRANSPARENT,(0x7c00,0x001f,0x03e0,0x7c00))
        self.assertEqual(len(PALETTE4),16)
        self.assertEqual(len(PALETTE8),256)
        region=[expected_pixel(x,y) for y in range(79,86) for x in range(39,96)]
        self.assertEqual(len(region),399)
        self.assertEqual(region.count(0),335)
        self.assertEqual(sum(v!=0 for v in region),64)

    def test_read_only_mmio_observer_and_strict_frontend_pre_raster_gate(self):
        patched=patch_memory(stub_memory())
        self.assertIn("vh168_expected_gp0_pc[]",patched)
        self.assertIn("vh168_expected_gp0_word[]",patched)
        self.assertIn("vh168_note_clut_mips_sw(regs,mem,value)",patched)
        self.assertLess(patched.index("if(vh168_active) vh168_note_clut_mips_sw"),
                        patched.index("vh138_pc_observe(regs,mem,value);"))
        self.assertIn("regs->pc!=vh168_expected_gp0_pc[vh168_gp0_count]+4u",patched)
        self.assertIn("value!=vh168_expected_gp0_word[vh168_gp0_count]",patched)
        with self.assertRaises(ValueError):
            patch_memory(patched)
        with self.assertRaises(ValueError):
            patch_memory(stub_memory().replace("vh138_pc_observe(regs,mem,value);",
                                               "vh138_pc_observe(regs,mem,0);"))
        front=patch_frontend(stub_frontend())
        for mark in ("--vh168-mips-clut-uv-vram","vh168_arm_clut_origin()!=0",
                     "vh168_disarm_clut_origin();","gp0_count!=211u",
                     "gp1_count!=1u || faults!=0u",
                     "VH168_CLUT_MIPS_GP0_REFUSED","VH168_GUEST_MIPS_CLUT_UV_VRAM_PASS",
                     "VH74_VRAM_PASS checked=399","checked!=399",
                     "vram[y*1024+x]!=expected","VH74_EXE_REFUSED"):
            self.assertIn(mark,front)
        self.assertLess(front.index("vh168_arm_clut_origin()!=0"),
                        front.index("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"))
        self.assertLess(front.index("vh168_disarm_clut_origin();"),
                        front.index("GPU_freeze(1,&snapshot,&vram)"))
        self.assertLess(front.index("if(wrong || checked!=399)"),
                        front.index("VH168_GUEST_MIPS_CLUT_UV_VRAM_PASS"))
        with self.assertRaises(ValueError):
            patch_frontend(front)

    def test_compiled_exact_origin_211_words_and_negative_cases(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("compiler unavailable")
        _,pcs,words,starts,_=expected_clut_source()
        c=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v){
 (void)r;(void)a;(void)v;
}
""" + patch_memory(stub_memory()) + r"""
int main(void){
    psxRegisters cpu={0};
    cpu.code=0xad090000u;
    if(vh168_arm_clut_origin()!=0 || vh168_arm_clut_origin()==0)return 1;
    cpu.pc=VH168_START_GP1;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    for(unsigned i=0;i<VH168_LENGTH;i++){
       cpu.pc=vh168_expected_gp0_pc[i]+4u;
       psxMemWrite32(&cpu,0x1f801810u,vh168_expected_gp0_word[i]);
    }
    /* A normal guest completion marker is not a GPU instruction. */
    psxMemWrite32(&cpu,0x80011000u,0x70000001u);
    if(vh168_clut_gp0_count()!=211u || vh168_clut_gp1_count()!=1u ||
       vh168_clut_fault_count()!=0u || vh168_disarm_clut_origin()!=0)
       return 2;
    if(vh168_disarm_clut_origin()==0)return 3;

    /* GP0 before GP1 reset must fail. */
    if(vh168_arm_clut_origin()!=0)return 4;
    cpu.pc=vh168_expected_gp0_pc[0]+4u;
    psxMemWrite32(&cpu,0x1f801810u,vh168_expected_gp0_word[0]);
    if(vh168_clut_gp0_count()!=0u || vh168_clut_fault_count()!=1u)return 5;
    if(vh168_disarm_clut_origin()!=0)return 6;

    if(vh168_arm_clut_origin()!=0)return 7;
    cpu.pc=VH168_START_GP1;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    cpu.pc=vh168_expected_gp0_pc[0]+8u;
    psxMemWrite32(&cpu,0x1f801810u,vh168_expected_gp0_word[0]);
    cpu.pc=vh168_expected_gp0_pc[0]+4u;
    cpu.code=0;
    psxMemWrite32(&cpu,0x1f801810u,vh168_expected_gp0_word[0]);
    cpu.code=0xad090000u;
    psxMemWrite32(&cpu,0x1f801810u,vh168_expected_gp0_word[0]^1u);
    if(vh168_clut_gp0_count()!=0u || vh168_clut_fault_count()!=3u)return 8;
    if(vh168_disarm_clut_origin()!=0)return 9;

    if(vh168_arm_clut_origin()!=0)return 10;
    cpu.pc=VH168_START_GP1;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    for(unsigned i=0;i<VH168_LENGTH;i++){
       cpu.pc=vh168_expected_gp0_pc[i]+4u;
       psxMemWrite32(&cpu,0x1f801810u,vh168_expected_gp0_word[i]);
    }
    psxMemWrite32(&cpu,0x1f801810u,0x2d000000u);
    if(vh168_clut_gp0_count()!=211u || vh168_clut_fault_count()!=1u)
       return 11;
    if(vh168_disarm_clut_origin()!=0)return 12;
    puts("VH168_COMPILED_CLUT_UV_SW_PROOF_PASS gp0_words=211 gp1=1 ft4=4 a0_uploads=4 bad_pc_refused=1 bad_opcode_refused=1 wrong_gp0_refused=1 extra_refused=1 missing_gp1_refused=1 original_retail=0");
    return 0;
}
""".replace("VH168_START_GP1",f"0x{expected_clut_source()[0]+4:08x}u")
        with tempfile.TemporaryDirectory(prefix="vh168-clut-") as td:
            d=Path(td)
            (d/"clut.c").write_text(c)
            exe=d/"clut"
            compiled=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(d/"clut.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=40)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn("VH168_COMPILED_CLUT_UV_SW_PROOF_PASS",run.stdout)

    def test_pinned_full_native_clut_uv_positive_and_mutation_gates(self):
        f=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v168-mips-clut-uv-vram.yml").read_text()
        for value in ("apply_map02_v168_mips_clut_uv_vram",
                      "test_map02_v168_mips_clut_uv_vram.py",
                      "--vh168-mips-clut-uv-vram",
                      "V168_SYNTHETIC.EXE","V168_BAD_CLUT.EXE",
                      "VH168_GUEST_MIPS_CLUT_UV_VRAM_PASS",
                      "VH168_CLUT_MIPS_GP0_REFUSED",
                      "VH74_VRAM_PASS checked=399"):
            self.assertIn(value,f)
        self.assertIn("test_map02_v167_mips_ft4_texture_vram.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
