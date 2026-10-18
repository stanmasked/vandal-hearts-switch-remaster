#!/usr/bin/env python3
"""v155: source-bound four-opcode native CPU quota and mutation regressions."""
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
    four_source_words,patch_interpreter,patch_frontend
)


class FourNativeSyntheticInstructions(unittest.TestCase):
    def test_four_words_exactly_derive_from_synthetic_source(self):
        words=four_source_words()
        self.assertEqual(len(words),4)
        self.assertNotEqual(words[3],0)
        native=patch_interpreter(v154(v153(native_opcode_witness())))
        self.assertIn("static const u32 vh152_words[4]={",native)
        for word in words:
            self.assertIn("0x%08xu"%word,native)
        self.assertIn("vh155_four_enabled ? 4u : 3u",native)
        self.assertIn("[0x1000cu]^=1u;",native)
        self.assertIn("vh152_matches==3u",native)
        with self.assertRaises(ValueError):
            patch_interpreter(native)

    def test_c_compiled_three_legacy_four_positive_and_fourth_mutation(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("C compiler unavailable")
        core=patch_interpreter(v154(v153(native_opcode_witness())))
        words=",".join("0x%08xu"%x for x in four_source_words())
        program=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {
    struct { unsigned char *psxM; } ptrs;
    u32 pc;
    unsigned stop,branchSeen;
} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
'''+NATIVE_GUARD+core+r'''
static void fill(unsigned char *ram) {
    static const u32 source[4]={SYNTH_WORDS};
    unsigned i,j;
    for(i=0u;i<4u;i++)
      for(j=0u;j<4u;j++)
        ram[0x10000u+4u*i+j]=(unsigned char)(source[i]>>(j*8u));
}
int main(void) {
    static const u32 words[4]={SYNTH_WORDS};
    unsigned char ram[0x12000]={0};
    psxRegisters regs={0};
    unsigned i;
    regs.ptrs.psxM=ram;
    fill(ram);

    /* Exact compatibility with v152's original three-source-word limit. */
    if(vh152_arm()!=0) return 1;
    for(i=0u;i<3u;i++)
        if(!vh152_before_dispatch(&regs,0x80010000u+4u*i,words[i])) return 2;
    if(vh152_before_dispatch(&regs,0x8001000cu,words[3])) return 3;
    if(vh152_matched_count()!=3u || !vh152_faulted()) return 4;
    vh152_disarm();
    regs.stop=regs.branchSeen=0u;

    /* Positive: same bounded native guard, now 4 exactly sourced words. */
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh150_arm(0x80010000u,0x80012000u,4u)!=0) return 5;
    for(i=0u;i<4u;i++) {
        regs.pc=0x80010000u+4u*i;
        if(!vh150_before(&regs,regs.pc) ||
           !vh152_before_dispatch(&regs,regs.pc,words[i])) return 6;
    }
    if(vh152_matched_count()!=4u || vh152_faulted()!=0u ||
       vh150_steps()!=4u) return 7;
    regs.pc=0x80010010u;
    if(vh150_before(&regs,regs.pc)) return 8;
    if(vh150_stop_reason()!=1u || vh150_steps()!=4u ||
       !regs.stop || !regs.branchSeen) return 9;
    vh152_disarm();vh150_disarm();
    regs.stop=regs.branchSeen=0u;

    /* Negative: first 3 dispatch; next guest RAM instruction altered. */
    fill(ram);
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh150_arm(0x80010000u,0x80012000u,4u)!=0) return 10;
    vh155_arm_fourth_mutation();
    for(i=0u;i<3u;i++) {
        regs.pc=0x80010000u+4u*i;
        if(!vh150_before(&regs,regs.pc) ||
           !vh152_before_dispatch(&regs,regs.pc,words[i])) return 11;
    }
    if(ram[0x1000cu]!=(unsigned char)((words[3]&255u)^1u)) return 12;
    regs.pc=0x8001000cu;
    if(!vh150_before(&regs,regs.pc)) return 13;
    if(vh152_before_dispatch(&regs,regs.pc,words[3]^1u)) return 14;
    if(vh152_matched_count()!=3u || !vh152_faulted() ||
       vh150_steps()!=4u || vh150_stop_reason()!=0u ||
       !regs.stop || !regs.branchSeen) return 15;
    if(vh152_before_dispatch(&regs,regs.pc,words[3])) return 16;
    vh152_disarm();vh150_disarm();
    puts("VH155_COMPILED_FOUR_NATIVE_PASS four=4 budget_stops_fifth=1 fourth_mutation_refused=1 old_three_preserved=1 original_retail=0");
    return 0;
}
'''.replace("SYNTH_WORDS",words)
        with tempfile.TemporaryDirectory(prefix="vh155-native-") as t:
            p=Path(t)
            (p/"native.c").write_text(program)
            build=subprocess.run([cc,"-std=c99","-Wall","-Wextra","-Werror",
                                   "-pedantic",str(p/"native.c"),"-o",str(p/"native")],
                                 capture_output=True,text=True,timeout=40)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(p/"native")],
                               capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("VH155_COMPILED_FOUR_NATIVE_PASS",run.stdout)

    def test_frontend_synthetic_profile_and_prior_modes_preserved(self):
        sample=(
            "\tint vh154_mutate_third_word = 0;\n"
            '\t\telse if (!strcmp(argv[i], "--vh154-mutate-third-word"))\n'
            "    if(vh154_mutate_third_word &&\n"
            "            if(vh154_mutate_third_word)\n"
            "                vh154_arm_third_word_mutation();\n"
            "            if(vh150_arm(0x80010000u,0x80012000u,3u)!=0){\n"
            "            vh152_disarm();\n"
            "            if(vh154_mutate_third_word){\n"
        )
        actual=patch_frontend(sample)
        self.assertIn("VH155_INVALID_MODE_REFUSED",actual)
        self.assertIn("VH155_NATIVE_FOUR_STEP_PASS",actual)
        self.assertIn("VH155_NATIVE_FOURTH_WORD_REFUSED",actual)
        self.assertIn("vh155_four_instructions ? 4u : 3u",actual)
        self.assertIn("witnessed!=4u || steps!=4u || reason!=1u",actual)
        self.assertIn("witnessed!=3u || steps!=4u",actual)
        self.assertLess(actual.index("vh155_enable_four();") if "vh155_enable_four();" in actual else actual.index("vh155_enable_four()!=0"),
                        actual.index("if(vh150_arm("))
        with self.assertRaises(ValueError):
            patch_frontend(actual)

    def test_native_ci_includes_positive_negative_and_legacy_cases(self):
        full=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v155-four-instruction-native.yml").read_text()
        for phrase in (
            "apply_map02_v155_four_instruction_native",
            "VH155_NATIVE_FOUR_STEP_PASS",
            "VH155_NATIVE_FOURTH_WORD_REFUSED",
            "--vh155-four-instructions",
            "--vh155-mutate-fourth-word",
            "VH154_NATIVE_THIRD_WORD_REFUSED",
            "VH150_NATIVE_BOUNDED_INTERPRETER_PASS",
        ):
            self.assertIn(phrase,full)
        self.assertIn("test_map02_v155_four_instruction_native.py",isolated)
        self.assertIn("original_retail_executed=0",isolated)


if __name__=="__main__":
    unittest.main()
