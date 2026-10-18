#!/usr/bin/env python3
"""v170: native source-authored FT4 layering CLUT E1/E2/E6 state and VRAM."""
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
from tools.apply_map02_v170_mips_ft4_gpu_state import (
    expected_order_source,patch_memory,patch_frontend,gpu_state_mmio_c
)
from tools.make_map02_v76_gpu_state_order_exe import (
    build,GP0_SEQUENCE,REGIONS,expected_pixel,BLEND_RED_THEN_GREEN,
    BLEND_GREEN_THEN_RED
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
    return ('\tint vh169_stp_e2v_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh169-mips-stp-e2v-vram"))\n'
            '\tif (loadst_f) {\n')


class GuestFT4StateOrder170(unittest.TestCase):
    def test_exact_202_guest_mips_sw_pcs_gpu_layered_e1_e2_e6_order(self):
        gp1,pcs,words,stop=expected_order_source()
        image,end,program=build()
        self.assertEqual(stop,end)
        self.assertEqual(len(image),6144)
        self.assertEqual(tuple(words),GP0_SEQUENCE)
        self.assertEqual(len(words),202)
        self.assertEqual(len(set(pcs)),202)
        self.assertEqual(program[4],sw(9,0,8))
        self.assertEqual(gp1,START+4*4)
        for i,pc in enumerate(pcs):
            self.assertEqual(pc,START+4*(8+3*i))
            self.assertEqual(program[(pc-START)//4],sw(9,0,8))
        self.assertEqual(sum(i==sw(9,0,8) for i in program),203)
        self.assertEqual((words[126],words[136]),(0xe2000401,0xe2000000))
        self.assertEqual((words[146],words[156],words[166]),
                         (0xe6000001,0xe6000002,0xe6000000))
        self.assertEqual((words[185],words[190],words[195]),
                         (0xe1000000,0xe1000020,0xe1000000))
        self.assertEqual(words[-2:],(0xe2000000,0xe6000000))
        self.assertEqual(sum((v>>24) in (0x2d,0x2f) for v in words),12)
        self.assertEqual(words.count(0x67ffffff),3)
        self.assertEqual(words.count(0x60ff0000),11)
        self.assertEqual(words.count(0xa0000000),3)

    def test_eleven_exact_layering_state_regions_and_guard_samples(self):
        self.assertEqual(len(REGIONS),11)
        self.assertNotEqual(BLEND_RED_THEN_GREEN,BLEND_GREEN_THEN_RED)
        sample=[expected_pixel(x,y) for y in range(127,134)
                for x in range(39,205)]
        self.assertEqual(len(sample),1162)
        self.assertEqual(sum(color!=0 for color in sample),176)
        self.assertEqual(sample.count(0),986)
        for name,x,color in REGIONS:
            self.assertEqual(
                [expected_pixel(px,128) for px in range(x,x+4)],
                [color]*4)

    def test_read_only_native_mmio_source_then_independent_vram_oracle(self):
        mem=patch_memory(fake_memory())
        for token in (
            "vh170_source_pc[]","vh170_source_word[]",
            "vh170_observe_state_mips_sw(regs,mem,value)",
            "regs->pc!=vh170_source_pc[vh170_seen]+4u",
            "value!=vh170_source_word[vh170_seen]",
        ):
            self.assertIn(token,mem)
        self.assertLess(mem.index("if(vh170_active) vh170_observe_state_mips_sw"),
                        mem.index("vh138_pc_observe(regs,mem,value);"))
        with self.assertRaises(ValueError):
            patch_memory(mem)
        with self.assertRaises(ValueError):
            patch_memory(fake_memory().replace(
                "vh138_pc_observe(regs,mem,value);",
                "vh138_pc_observe(regs,mem,0);"))
        frontend=patch_frontend(fake_frontend())
        for needle in (
            "--vh170-mips-ft4-gpu-state",
            "vh170_arm_state_source()!=0",
            "vh170_disarm_state_source();",
            "words!=202u || gp1_count!=1u || faults!=0u",
            "VH170_MIPS_GPU_STATE_REFUSED",
            "VH170_GUEST_MIPS_GPU_STATE_VRAM_PASS",
            "VH76_VRAM_PASS checked=1162 regions=11 region_pixels=176 guard=986",
            "checked!=1162 || total_bad",
            "vram[y*1024+x]!=wanted",
            "VH76_EXE_REFUSED",
        ):
            self.assertIn(needle,frontend)
        self.assertLess(frontend.index("vh170_arm_state_source()!=0"),
                        frontend.index("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"))
        self.assertLess(frontend.index("vh170_disarm_state_source();"),
                        frontend.index("GPU_freeze(1,&freeze,&vram)"))
        self.assertLess(frontend.index("if(checked!=1162 || total_bad)"),
                        frontend.index("VH170_GUEST_MIPS_GPU_STATE_VRAM_PASS"))
        with self.assertRaises(ValueError):patch_frontend(frontend)

    def test_compiled_202_words_mmio_origin_and_fail_closed_corruption(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):self.skipTest("C compiler unavailable")
        c=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 mem,u32 value){
 (void)r;(void)mem;(void)value;
}
""" + patch_memory(fake_memory()) + r"""
int main(void) {
    psxRegisters cpu={0};
    cpu.code=0xad090000u;
    if(vh170_arm_state_source()!=0 || vh170_arm_state_source()==0)return 1;
    cpu.pc=VH170_GP1_RESET_PC;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    for(unsigned i=0;i<VH170_WORDS;i++){
        cpu.pc=vh170_source_pc[i]+4u;
        psxMemWrite32(&cpu,0x1f801810u,vh170_source_word[i]);
    }
    psxMemWrite32(&cpu,0x80011000u,0x70000001u);
    if(vh170_state_gp0_seen()!=202u || vh170_state_gp1_seen()!=1u ||
       vh170_state_fault_count()!=0u || vh170_disarm_state_source()!=0)
        return 2;
    if(vh170_disarm_state_source()==0)return 3;
    if(vh170_arm_state_source()!=0)return 4;
    cpu.pc=vh170_source_pc[0]+4u;
    psxMemWrite32(&cpu,0x1f801810u,vh170_source_word[0]);
    if(vh170_state_gp0_seen()!=0u || vh170_state_fault_count()!=1u)return 5;
    if(vh170_disarm_state_source()!=0)return 6;
    if(vh170_arm_state_source()!=0)return 7;
    cpu.pc=VH170_GP1_RESET_PC;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    cpu.pc=vh170_source_pc[0]+8u;
    psxMemWrite32(&cpu,0x1f801810u,vh170_source_word[0]);
    cpu.pc=vh170_source_pc[0]+4u;cpu.code=0u;
    psxMemWrite32(&cpu,0x1f801810u,vh170_source_word[0]);
    cpu.code=0xad090000u;
    psxMemWrite32(&cpu,0x1f801810u,vh170_source_word[0]^2u);
    if(vh170_state_gp0_seen()!=0u || vh170_state_fault_count()!=3u)return 8;
    if(vh170_disarm_state_source()!=0)return 9;
    if(vh170_arm_state_source()!=0)return 10;
    cpu.pc=VH170_GP1_RESET_PC;
    psxMemWrite32(&cpu,0x1f801814u,0x01000000u);
    for(unsigned i=0;i<VH170_WORDS;i++){
        cpu.pc=vh170_source_pc[i]+4u;
        psxMemWrite32(&cpu,0x1f801810u,vh170_source_word[i]);
    }
    psxMemWrite32(&cpu,0x1f801810u,0xe6000002u);
    if(vh170_state_gp0_seen()!=202u || vh170_state_fault_count()!=1u)return 11;
    if(vh170_disarm_state_source()!=0)return 12;
    puts("VH170_COMPILED_MIPS_GPU_STATES_PASS gp0_words=202 gp1=1 ft4=12 sprites=3 states=e1_e2_e6 bad_pc_refused=1 bad_opcode_refused=1 bad_word_refused=1 extra_refused=1 missing_gp1_refused=1 original_retail=0");
    return 0;
}
""".replace("VH170_GP1_RESET_PC",f"0x{expected_order_source()[0]+4:08x}u")
        with tempfile.TemporaryDirectory(prefix="vh170-states-") as td:
            base=Path(td);(base/"fixture.c").write_text(c);exe=base/"fixture"
            result=subprocess.run([cc,"-std=c99","-pedantic","-Wall",
                "-Wextra","-Werror",str(base/"fixture.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=40)
            self.assertEqual(result.returncode,0,result.stderr)
            executed=subprocess.run([str(exe)],capture_output=True,
                                    text=True,timeout=10)
            self.assertEqual(executed.returncode,0,
                             executed.stdout+executed.stderr)
            self.assertIn("VH170_COMPILED_MIPS_GPU_STATES_PASS",executed.stdout)

    def test_pinned_native_gcc_clang_and_one_guest_e6_instruction_mutation(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v170-mips-ft4-gpu-state.yml").read_text()
        for word in (
            "apply_map02_v170_mips_ft4_gpu_state",
            "test_map02_v170_mips_ft4_gpu_state.py",
            "--vh170-mips-ft4-gpu-state",
            "V170_SYNTHETIC.EXE","V170_BAD_E6.EXE",
            "VH170_GUEST_MIPS_GPU_STATE_VRAM_PASS",
            "VH170_MIPS_GPU_STATE_REFUSED",
            "VH76_VRAM_PASS checked=1162",
        ):
            self.assertIn(word,native)
        self.assertIn("test_map02_v169_mips_stp_e2v_vram.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
