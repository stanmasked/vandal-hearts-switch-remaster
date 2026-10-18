#!/usr/bin/env python3
"""v156: compiled source-derived MIPS register semantics and native CI coverage."""
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

from tools.apply_map02_v150_native_instruction_budget import NATIVE_GUARD
from tools.apply_map02_v152_fetch_opcode_witness import native_opcode_witness
from tools.apply_map02_v153_second_instruction_mutation import patch_interpreter as v153
from tools.apply_map02_v154_third_instruction_mutation import patch_interpreter as v154
from tools.apply_map02_v155_four_instruction_native import (
    patch_interpreter as v155, four_source_words
)
from tools.apply_map02_v156_register_checkpoints import (
    expected_register_checkpoints, patch_interpreter, patch_frontend
)


class SourceBoundNativeMipsRegisters(unittest.TestCase):
    def test_register_checkpoints_derived_from_first_four_source_words(self):
        self.assertEqual(
            expected_register_checkpoints(),
            (0x1f800000,0x1f801810,0xe3000000,0xe3000000))
        w=four_source_words()
        self.assertEqual(tuple(w),
            (0x3c081f80,0x35081810,0x3c09e300,0x35290000))
        src=patch_interpreter(v155(v154(v153(native_opcode_witness()))))
        self.assertIn("regs->GPR.r[8]==0x1f800000u",src)
        self.assertIn("regs->GPR.r[8]==0x1f801810u",src)
        self.assertIn("regs->GPR.r[9]==0xe3000000u",src)
        self.assertIn("regs->GPR.r[8]^=1u;",src)
        self.assertLess(src.index("vh156_verify_previous_effects(regs,pc)"),
                        src.index("idx=(pc-0x80010000u)/4u;"))
        with self.assertRaises(ValueError):
            patch_interpreter(src)

    def test_compiled_gcc_clang_register_effects_and_tamper(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("native C compiler unavailable")
        inner=patch_interpreter(v155(v154(v153(native_opcode_witness()))))
        words=",".join("0x%08xu"%x for x in four_source_words())
        test=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {
    struct { unsigned char *psxM; } ptrs;
    union { u32 r[34]; } GPR;
    u32 pc;
    unsigned stop,branchSeen;
} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
'''+NATIVE_GUARD+inner+r'''
static const u32 words[4]={SOURCE_WORDS};
static void reset_ram(unsigned char *ram){
    unsigned i,j;
    for(i=0u;i<4u;i++)
      for(j=0u;j<4u;j++)
        ram[0x10000u+4u*i+j]=(unsigned char)(words[i]>>(8u*j));
}
static void simulate_mips_lui_ori(psxRegisters *r,u32 word){
    unsigned op=word>>26u, rs=(word>>21u)&31u, rt=(word>>16u)&31u;
    if(op==15u) r->GPR.r[rt]=(word&0xffffu)<<16u;
    else if(op==13u) r->GPR.r[rt]=r->GPR.r[rs]|(word&0xffffu);
}
int main(void){
    unsigned char ram[0x12000]={0};
    psxRegisters r={0};
    unsigned i;
    r.ptrs.psxM=ram;
    reset_ram(ram);

    /* Positive: real host GPR effects after all four verified words. */
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh156_arm_register_check(0)!=0 ||
       vh150_arm(0x80010000u,0x80012000u,4u)!=0) return 1;
    for(i=0u;i<4u;i++){
        r.pc=0x80010000u+4u*i;
        if(!vh150_before(&r,r.pc) ||
           !vh152_before_dispatch(&r,r.pc,words[i])) return 2;
        simulate_mips_lui_ori(&r,words[i]);
    }
    if(r.GPR.r[8]!=0x1f801810u || r.GPR.r[9]!=0xe3000000u ||
       vh152_matched_count()!=4u || vh152_faulted()) return 3;
    if(vh150_before(&r,0x80010010u) ||
       vh150_stop_reason()!=1u || vh150_steps()!=4u) return 4;
    vh152_disarm();vh150_disarm();r.stop=r.branchSeen=0u;

    /* Negative: actual value changed after first LUI and before next ORI. */
    reset_ram(ram);
    r.GPR.r[8]=r.GPR.r[9]=0u;
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh156_arm_register_check(1)!=0 ||
       vh150_arm(0x80010000u,0x80012000u,4u)!=0) return 5;
    if(!vh150_before(&r,0x80010000u) ||
       !vh152_before_dispatch(&r,0x80010000u,words[0])) return 6;
    simulate_mips_lui_ori(&r,words[0]);
    if(!vh150_before(&r,0x80010004u) ||
       vh152_before_dispatch(&r,0x80010004u,words[1])) return 7;
    if(vh152_matched_count()!=1u || !vh152_faulted() ||
       vh150_steps()!=2u || vh150_stop_reason()!=0u ||
       !r.stop || !r.branchSeen) return 8;
    if(vh152_before_dispatch(&r,0x80010004u,words[1])) return 9;
    vh152_disarm();vh150_disarm();r.stop=r.branchSeen=0u;

    /* Negative: unexpected GPR update is denied even without test injection. */
    r.GPR.r[8]=r.GPR.r[9]=0u;
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh156_arm_register_check(0)!=0) return 10;
    if(!vh152_before_dispatch(&r,0x80010000u,words[0])) return 11;
    if(vh152_before_dispatch(&r,0x80010004u,words[1]) ||
       vh152_matched_count()!=1u || !vh152_faulted()) return 12;
    vh152_disarm();
    puts("VH156_COMPILED_REGISTER_SEMANTICS_PASS source=4 checkpoints=3 corruption_refused=1 latched=1 original_retail=0");
    return 0;
}
'''.replace("SOURCE_WORDS",words)
        with tempfile.TemporaryDirectory(prefix="vh156-registers-") as t:
            root=Path(t)
            (root/"test.c").write_text(test)
            exe=root/"test"
            cc_result=subprocess.run([cc,"-std=c99","-Wall","-Wextra",
                "-Werror","-pedantic",str(root/"test.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=40)
            self.assertEqual(cc_result.returncode,0,cc_result.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("VH156_COMPILED_REGISTER_SEMANTICS_PASS",run.stdout)

    def test_frontend_register_test_is_synthetic_four_mode_only(self):
        sample=(
            "\tint vh155_mutate_fourth_word = 0;\n"
            '\t\telse if (!strcmp(argv[i], "--vh155-four-instructions"))\n'
            "    if((vh155_four_instructions || vh155_mutate_fourth_word) &&\n"
            "                if(vh155_mutate_fourth_word)\n"
            "                    vh155_arm_fourth_mutation();\n"
            "                if(vh155_mutate_fourth_word){\n"
        )
        result=patch_frontend(sample)
        self.assertIn("VH156_INVALID_MODE_REFUSED",result)
        self.assertIn("VH156_NATIVE_REGISTER_EFFECTS_PASS",result)
        self.assertIn("VH156_NATIVE_REGISTER_CORRUPTION_REFUSED",result)
        self.assertIn("vh156_arm_register_check(",result)
        self.assertIn("vh152_mutate_post_verify || vh153_mutate_second_word",result)
        self.assertIn("psxRegs.GPR.r[8]!=0x1f801810u",result)
        self.assertIn("psxRegs.GPR.r[9]!=0xe3000000u",result)
        with self.assertRaises(ValueError):
            patch_frontend(result)

    def test_real_pcsx_wires_positive_negative_and_old_modes(self):
        wf=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        split=(ROOT/".github/workflows/map02-v156-register-checkpoints.yml").read_text()
        for marker in (
            "apply_map02_v156_register_checkpoints",
            "VH156_NATIVE_REGISTER_EFFECTS_PASS",
            "VH156_NATIVE_REGISTER_CORRUPTION_REFUSED",
            "--vh156-verify-register-effects",
            "--vh156-corrupt-t0-second",
            "VH155_NATIVE_FOUR_STEP_PASS",
            "VH155_NATIVE_FOURTH_WORD_REFUSED",
        ):
            self.assertIn(marker,wf)
        self.assertIn("test_map02_v156_register_checkpoints.py",split)
        self.assertIn("original_retail_executed=0",split)


if __name__=="__main__":
    unittest.main()
