#!/usr/bin/env python3
"""Compiled native v154 third-opcode refusal plus pinned PCSX workflow gate."""
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
from tools.apply_map02_v152_fetch_opcode_witness import (
    expected_first_three_words, native_opcode_witness
)
from tools.apply_map02_v153_second_instruction_mutation import (
    patch_interpreter as patch_v153
)
from tools.apply_map02_v154_third_instruction_mutation import (
    patch_interpreter, patch_frontend
)


class ThirdInstructionMutation(unittest.TestCase):
    def test_compiled_witness_refuses_third_after_two_accepted(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("no native C compiler")
        code=patch_interpreter(patch_v153(native_opcode_witness()))
        sample=",".join("0x%08xu"%w for w in expected_first_three_words())
        program=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct { struct { unsigned char *psxM; } ptrs;
                 unsigned stop,branchSeen; } psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
'''+code+r'''
int main(void){
    unsigned char ram[0x12000]={0};
    psxRegisters regs={0};
    static const u32 source[3]={SOURCE_WORDS};
    unsigned i,j;
    regs.ptrs.psxM=ram;
    for(i=0u;i<3u;i++)
      for(j=0u;j<4u;j++)
        ram[0x10000u+4u*i+j]=(unsigned char)(source[i]>>(8u*j));
    if(vh152_arm()!=0) return 1;
    vh154_arm_third_word_mutation();
    if(!vh152_before_dispatch(&regs,0x80010000u,source[0])) return 2;
    if(!vh152_before_dispatch(&regs,0x80010004u,source[1])) return 3;
    if(vh152_matched_count()!=2u || vh152_faulted()!=0u) return 4;
    if(ram[0x10008u]!=(unsigned char)((source[2]&0xffu)^1u)) return 5;
    if(vh152_before_dispatch(&regs,0x80010008u,source[2]^1u)) return 6;
    if(vh152_matched_count()!=2u || !vh152_faulted() ||
       !regs.stop || !regs.branchSeen) return 7;
    if(vh152_before_dispatch(&regs,0x80010008u,source[2])) return 8;
    vh152_disarm();
    puts("VH154_COMPILED_THIRD_WORD_PASS matched=2 attempted=3 rejected=1 latched=1");
    return 0;
}
'''.replace("SOURCE_WORDS",sample)
        with tempfile.TemporaryDirectory(prefix="vh154-witness-") as t:
            td=Path(t)
            (td/"probe.c").write_text(program)
            compile=subprocess.run([cc,"-std=c99","-Wall","-Wextra",
                    "-Werror","-pedantic",str(td/"probe.c"),"-o",str(td/"probe")],
                    capture_output=True,text=True,timeout=30)
            self.assertEqual(compile.returncode,0,compile.stderr)
            run=subprocess.run([str(td/"probe")],
                        capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("VH154_COMPILED_THIRD_WORD_PASS",run.stdout)

    def test_mutation_patch_is_single_install_fail_closed(self):
        original=patch_v153(native_opcode_witness())
        changed=patch_interpreter(original)
        self.assertIn("[0x10008u]^=1u;",changed)
        self.assertIn("vh152_matches==2u",changed)
        self.assertIn("vh154_arm_third_word_mutation",changed)
        self.assertIn("vh154_mutate_third_word=0u;",changed)
        with self.assertRaises(ValueError):
            patch_interpreter(changed)

    def test_frontend_only_accepts_isolated_synthetic_flag(self):
        sample=(
            "\tint vh153_mutate_second_word = 0;\n"
            '\t\telse if (!strcmp(argv[i], "--vh153-mutate-second-word"))\n'
            "    if(vh153_mutate_second_word &&\n"
            "            if(vh153_mutate_second_word)\n"
            "                vh153_arm_second_word_mutation();\n"
            "            if(vh153_mutate_second_word){\n"
            "                if(!faulted || witnessed!=1u || vh150_steps()!=2u){"
        )
        result=patch_frontend(sample)
        self.assertIn("VH154_INVALID_MODE_REFUSED",result)
        self.assertIn("VH154_NATIVE_THIRD_WORD_REFUSED",result)
        self.assertIn("witnessed!=2u || vh150_steps()!=3u",result)
        self.assertIn("vh152_mutate_post_verify || vh153_mutate_second_word",result)
        self.assertIn("vh154_arm_third_word_mutation();",result)
        with self.assertRaises(ValueError):
            patch_frontend(result)

    def test_full_native_workflow_keeps_earlier_modes_and_third_mutation(self):
        full=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v154-third-instruction-mutation.yml").read_text()
        for marker in (
            "apply_map02_v154_third_instruction_mutation",
            "VH154_NATIVE_THIRD_WORD_REFUSED",
            "--vh154-mutate-third-word",
            "matched=2 attempted=3 original_retail=0",
            "VH153_NATIVE_SECOND_WORD_REFUSED",
            "VH152_NATIVE_FETCH_TAMPER_REFUSED",
        ):
            self.assertIn(marker,full)
        self.assertIn("test_map02_v154_third_instruction_mutation.py",isolated)
        self.assertIn("original_retail_executed=0",isolated)


if __name__=="__main__":
    unittest.main()
