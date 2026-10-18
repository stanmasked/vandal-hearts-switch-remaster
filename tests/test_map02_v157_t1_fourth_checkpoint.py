#!/usr/bin/env python3
"""v157: native pre-dispatch t1 register corruption after three source words."""
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
    patch_interpreter as v155,four_source_words
)
from tools.apply_map02_v156_register_checkpoints import patch_interpreter as v156
from tools.apply_map02_v157_t1_fourth_checkpoint import (
    patch_interpreter, patch_frontend
)


class FourthOpcodeT1Corruption(unittest.TestCase):
    def test_compiled_c_register_observer_refuses_fourth_opcode(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("C compiler missing")
        core=patch_interpreter(v156(v155(v154(v153(native_opcode_witness())))))
        words=",".join("0x%08xu"%x for x in four_source_words())
        program=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {
    union { u32 r[34]; } GPR;
    u32 pc;
    unsigned stop,branchSeen;
    struct { unsigned char *psxM; } ptrs;
} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
'''+NATIVE_GUARD+core+r'''
static const u32 words[4]={SOURCE_WORDS};
static void seed(unsigned char *ram){
    unsigned i,j;
    for(i=0u;i<4u;i++)
      for(j=0u;j<4u;j++)
        ram[0x10000u+i*4u+j]=(unsigned char)(words[i]>>(j*8u));
}
static void execute_source_lui_ori(psxRegisters *r,u32 opword){
    unsigned op=opword>>26u, rs=(opword>>21u)&31u, rt=(opword>>16u)&31u;
    if(op==15u) r->GPR.r[rt]=(opword&0xffffu)<<16u;
    else if(op==13u) r->GPR.r[rt]=r->GPR.r[rs]|(opword&0xffffu);
}
int main(void){
    unsigned char ram[0x12000]={0};
    psxRegisters r={0};
    unsigned i;
    r.ptrs.psxM=ram;
    seed(ram);

    /* Retained v156 positive: genuine semantics for all four words. */
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh156_arm_register_check(0)!=0 ||
       vh150_arm(0x80010000u,0x80012000u,4u)!=0) return 2;
    for(i=0u;i<4u;i++){
        r.pc=0x80010000u+4u*i;
        if(!vh150_before(&r,r.pc) ||
           !vh152_before_dispatch(&r,r.pc,words[i])) return 3;
        execute_source_lui_ori(&r,words[i]);
    }
    if(r.GPR.r[8]!=0x1f801810u || r.GPR.r[9]!=0xe3000000u ||
       vh152_matched_count()!=4u || vh152_faulted()!=0u) return 4;
    if(vh150_before(&r,0x80010010u) ||
       vh150_steps()!=4u || vh150_stop_reason()!=1u) return 5;
    vh152_disarm();vh150_disarm();
    r.stop=r.branchSeen=0u;
    r.GPR.r[8]=r.GPR.r[9]=0u;
    seed(ram);

    /* Negative: after three genuine dispatches, change t1 before fourth. */
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh156_arm_register_check(0)!=0 ||
       vh150_arm(0x80010000u,0x80012000u,4u)!=0) return 6;
    vh157_arm_t1_fourth();
    for(i=0u;i<3u;i++){
        r.pc=0x80010000u+4u*i;
        if(!vh150_before(&r,r.pc) ||
           !vh152_before_dispatch(&r,r.pc,words[i])) return 7;
        execute_source_lui_ori(&r,words[i]);
    }
    if(vh152_matched_count()!=3u || vh152_faulted() ||
       r.GPR.r[9]!=0xe3000000u) return 8;
    r.pc=0x8001000cu;
    if(!vh150_before(&r,r.pc) ||
       vh152_before_dispatch(&r,r.pc,words[3])) return 9;
    if(r.GPR.r[9]!=0xe3000001u || !vh152_faulted() ||
       vh152_matched_count()!=3u || vh150_steps()!=4u ||
       vh150_stop_reason()!=0u || !r.stop || !r.branchSeen) return 10;
    if(vh152_before_dispatch(&r,r.pc,words[3])) return 11;
    vh152_disarm();vh150_disarm();
    puts("VH157_COMPILED_T1_FOURTH_PASS first_three=3 fourth_refused=1 original_four_preserved=1 latched=1");
    return 0;
}
'''.replace("SOURCE_WORDS",words)
        with tempfile.TemporaryDirectory(prefix="vh157-native-") as temp:
            d=Path(temp)
            (d/"test.c").write_text(program)
            exe=d/"test"
            built=subprocess.run([cc,"-std=c99","-Wall","-Wextra","-Werror",
                "-pedantic",str(d/"test.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=40)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("VH157_COMPILED_T1_FOURTH_PASS",run.stdout)

    def test_native_interpreter_scoped_mutation_and_latched_refusal(self):
        prior=v156(v155(v154(v153(native_opcode_witness()))))
        patched=patch_interpreter(prior)
        self.assertIn("vh157_arm_t1_fourth",patched)
        self.assertIn("regs->GPR.r[9]^=1u;",patched)
        self.assertIn("pc==0x8001000cu",patched)
        self.assertIn("vh157_corrupt_t1_fourth=0u;",patched)
        with self.assertRaises(ValueError):
            patch_interpreter(patched)

    def test_frontend_rejects_invalid_modes_and_checks_count(self):
        sample=(
            "\tint vh156_corrupt_t0_second = 0;\n"
            '\t\telse if (!strcmp(argv[i], "--vh156-corrupt-t0-second"))\n'
            "    if((vh156_verify_register_effects || vh156_corrupt_t0_second) &&\n"
            "                if(vh156_verify_register_effects &&\n"
            "                   vh156_arm_register_check(\n"
            "                       (unsigned)vh156_corrupt_t0_second)!=0){\n"
            '                    SysPrintf("VH156_REGISTER_ARM_REFUSED\\n");\n'
            "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 60;\n"
            "                }\n"
            "                if(vh156_verify_register_effects){\n"
            "                    if(vh156_corrupt_t0_second){"
        )
        out=patch_frontend(sample)
        self.assertIn("VH157_INVALID_MODE_REFUSED",out)
        self.assertIn("VH157_NATIVE_T1_FOURTH_REFUSED",out)
        self.assertIn("witnessed!=3u",out)
        self.assertIn("steps!=4u || reason!=0u",out)
        self.assertIn("vh157_arm_t1_fourth();",out)
        with self.assertRaises(ValueError):
            patch_frontend(out)

    def test_native_pipeline_includes_positive_and_negative(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        small=(ROOT/".github/workflows/map02-v157-t1-fourth-checkpoint.yml").read_text()
        for x in (
            "apply_map02_v157_t1_fourth_checkpoint",
            "VH157_NATIVE_T1_FOURTH_REFUSED",
            "--vh157-corrupt-t1-fourth",
            "VH156_NATIVE_REGISTER_EFFECTS_PASS",
            "VH156_NATIVE_REGISTER_CORRUPTION_REFUSED",
            "VH155_NATIVE_FOUR_STEP_PASS",
        ):
            self.assertIn(x,workflow)
        self.assertIn("test_map02_v157_t1_fourth_checkpoint.py",small)
        self.assertIn("original_retail_executed=0",small)


if __name__=="__main__":
    unittest.main()
