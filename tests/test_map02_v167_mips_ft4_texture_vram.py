#!/usr/bin/env python3
"""v167 real self-authored MIPS GP0(A0), FT4, STP/ABR origins + Unai VRAM."""
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
from tools.apply_map02_v167_mips_ft4_texture_vram import (
    expected_ft4_source,ft4_mmio_c,ft4_oracle,patch_memory,patch_frontend,
)
from tools.make_map02_v72_ft4_mips_exe import GP0_SEQUENCE,build,MAGIC
from tools.make_map02_v70_synthetic_psx_exe import sw


def fake_memory() -> str:
    return """void vh140_mmio_enable(unsigned mutate_expected) {
    (void)mutate_expected;
}
void psxMemWrite32(psxRegisters *regs, u32 mem, u32 value) {
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
}
"""


def fake_frontend() -> str:
    return ('\tint vh166_mips_pc_gp0_vram_chain = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh166-mips-pc-gp0-vram-chain")) {\n'
            '\tif (loadst_f) {\n')


class GuestMipsFT4Origin167(unittest.TestCase):
    def test_source_authored_72_gp0_words_four_textured_ft4_and_mips_pcs(self):
        gp1pc,pcs,words,starts,loop=expected_ft4_source()
        image,program_pc,program=build()
        self.assertEqual(loop,program_pc)
        self.assertEqual(image[0x4c:0x54],MAGIC)
        self.assertEqual(len(image),4096)
        self.assertEqual(len(words),72)
        self.assertEqual(words,GP0_SEQUENCE)
        self.assertEqual(len(set(pcs)),72)
        self.assertEqual(starts,(36,45,54,63))
        self.assertEqual(program[(gp1pc-0x80010000)//4],sw(9,0,8))
        for i,(pc,word) in enumerate(zip(pcs,words)):
            index=(pc-0x80010000)//4
            self.assertEqual(index,8+3*i)
            self.assertEqual(program[index],sw(9,0,8))
            self.assertIn(program[index-2]>>26,(0x0f,))
            self.assertIn(program[index-1]>>26,(0x0d,))
        self.assertEqual([words[i] for i in starts],
                         [0x2d000000,0x2f000000,0x2f000000,0x2f000000])

    def test_pinned_native_mmio_insertion_is_bounded_and_nonmutating(self):
        patched=patch_memory(fake_memory())
        self.assertIn("vh167_source_gp0_pc[]",patched)
        self.assertIn("vh167_source_gp0_words[]",patched)
        self.assertIn("vh167_observe_ft4_origin(regs,mem,value)",patched)
        self.assertLess(patched.index("if(vh167_active) vh167_observe_ft4_origin"),
                        patched.index("vh138_pc_observe(regs,mem,value);"))
        self.assertIn("regs->code!=0xad090000u",patched)
        self.assertIn("val!=vh167_source_gp0_words[vh167_gp0_seen]",patched)
        with self.assertRaises(ValueError):
            patch_memory(patched)
        with self.assertRaises(ValueError):
            patch_memory(fake_memory().replace("vh138_pc_observe(regs,mem,value);",
                                              "vh138_pc_observe(regs,mem,0);"))

    def test_independent_real_unai_ft4_pixel_oracle_bound_after_cpu_trace(self):
        src=patch_frontend(fake_frontend())
        for term in (
            "--vh167-mips-ft4-texture-vram",
            "vh167_arm_ft4_origin()!=0",
            "vh167_disarm_ft4_origin();",
            "gp0_words!=72u || gp1_words!=1u || gp0_faults!=0u",
            "VH167_FT4_MIPS_GP0_REFUSED",
            "VH167_GUEST_MIPS_FT4_VRAM_PASS",
            "gp0_words=72 gp1_words=1 ft4=4 texture_upload=1",
            "pixels_checked=378 opaque=16 abr0=16 no_stp=16 abr1=16",
            "guard=314 original_retail=0",
            "VH72_FT4_VRAM_PASS checked=378",
            "vram[y*1024+x]!=expected",
            "VH72_EXE_REFUSED",
        ):
            self.assertIn(term,src)
        self.assertLess(src.index("vh167_arm_ft4_origin()!=0"),
                        src.index("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"))
        self.assertLess(src.index("vh167_disarm_ft4_origin();"),
                        src.index("GPU_freeze(1,&snapshot,&vram)"))
        self.assertLess(src.index("if(checked!=378 || wrong)"),
                        src.index("VH167_GUEST_MIPS_FT4_VRAM_PASS"))
        with self.assertRaises(ValueError):
            patch_frontend(src)

    def test_compiled_source_pc_word_gp1_and_wrong_ft4_negative_cases(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("compiler unavailable")
        program=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *regs,u32 address,u32 value) {
    (void)regs;(void)address;(void)value;
}
"""+patch_memory(fake_memory())+r"""
int main(void) {
    psxRegisters r={0};
    r.code=0xad090000u;
    if(vh167_arm_ft4_origin()!=0 ||
       vh167_arm_ft4_origin()==0) return 1;
    r.pc=VH167_GP1_PC_PLUS_4;
    psxMemWrite32(&r,0x1f801814u,0x01000000u);
    for(unsigned n=0;n<VH167_GP0_WORDS;n++){
        r.pc=vh167_source_gp0_pc[n]+4u;
        psxMemWrite32(&r,0x1f801810u,vh167_source_gp0_words[n]);
    }
    psxMemWrite32(&r,0x80011000u,0x70000001u);
    if(vh167_ft4_gp1_seen()!=1u || vh167_ft4_gp0_seen()!=72u ||
       vh167_ft4_faults() || vh167_disarm_ft4_origin()!=0 ||
       vh167_disarm_ft4_origin()==0)return 2;
    if(vh167_arm_ft4_origin()!=0)return 3;
    r.pc=vh167_source_gp0_pc[0]+4u;
    psxMemWrite32(&r,0x1f801810u,vh167_source_gp0_words[0]);
    if(vh167_ft4_gp0_seen()!=0u || vh167_ft4_faults()!=1u)return 4;
    if(vh167_disarm_ft4_origin()!=0)return 5;
    if(vh167_arm_ft4_origin()!=0)return 6;
    r.pc=VH167_GP1_PC_PLUS_4;
    psxMemWrite32(&r,0x1f801814u,0x01000000u);
    r.pc=vh167_source_gp0_pc[0]+8u;
    psxMemWrite32(&r,0x1f801810u,vh167_source_gp0_words[0]);
    r.pc=vh167_source_gp0_pc[0]+4u;
    r.code=0u;
    psxMemWrite32(&r,0x1f801810u,vh167_source_gp0_words[0]);
    r.code=0xad090000u;
    psxMemWrite32(&r,0x1f801810u,vh167_source_gp0_words[0]^1u);
    if(vh167_ft4_gp0_seen()!=0u || vh167_ft4_faults()!=3u)return 7;
    if(vh167_disarm_ft4_origin()!=0)return 8;
    if(vh167_arm_ft4_origin()!=0)return 9;
    r.pc=VH167_GP1_PC_PLUS_4;
    psxMemWrite32(&r,0x1f801814u,0x01000000u);
    for(unsigned n=0;n<VH167_GP0_WORDS;n++){
        r.pc=vh167_source_gp0_pc[n]+4u;
        psxMemWrite32(&r,0x1f801810u,vh167_source_gp0_words[n]);
    }
    psxMemWrite32(&r,0x1f801810u,0x2d000000u);
    if(vh167_ft4_gp0_seen()!=72u || vh167_ft4_faults()!=1u) return 10;
    if(vh167_disarm_ft4_origin()!=0)return 11;
    puts("VH167_COMPILED_FT4_MIPS_ORIGIN_PASS gp0_words=72 gp1=1 textured_quads=4 bad_pc=refused bad_opcode=refused bad_gp0=refused extra=refused missing=refused original_retail=0");
    return 0;
}
""".replace("VH167_GP1_PC_PLUS_4",f"0x{expected_ft4_source()[0]+4:08x}u")
        with tempfile.TemporaryDirectory(prefix="vh167-ft4-") as tmp:
            d=Path(tmp);(d/"fixture.c").write_text(program)
            exe=d/"fixture"
            b=subprocess.run([cc,"-std=c99","-pedantic","-Wall","-Wextra","-Werror",
                              str(d/"fixture.c"),"-o",str(exe)],
                             capture_output=True,text=True,timeout=35)
            self.assertEqual(b.returncode,0,b.stderr)
            r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn("VH167_COMPILED_FT4_MIPS_ORIGIN_PASS",r.stdout)

    def test_pinned_unai_ci_has_positive_and_changed_ft4_negative(self):
        w=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v167-mips-ft4-texture-vram.yml").read_text()
        for needle in (
            "apply_map02_v167_mips_ft4_texture_vram",
            "test_map02_v167_mips_ft4_texture_vram.py",
            "V167_SYNTHETIC.EXE",
            "--vh167-mips-ft4-texture-vram",
            "VH167_GUEST_MIPS_FT4_VRAM_PASS",
            "VH167_FT4_MIPS_GP0_REFUSED",
            "V167_BAD_FT4.EXE",
            "VH72_FT4_VRAM_PASS checked=378",
        ):
            self.assertIn(needle,w)
        self.assertIn("test_map02_v166_mips_pc_gp0_vram.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()
