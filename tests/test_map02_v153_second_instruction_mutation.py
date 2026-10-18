#!/usr/bin/env python3
"""v153: prove exactly one actual synthetic MIPS word accepted before refusal."""
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
    native_opcode_witness, expected_first_three_words
)
from tools.apply_map02_v153_second_instruction_mutation import (
    patch_frontend, patch_interpreter
)


class SecondInstructionMutation(unittest.TestCase):
    def test_compiled_native_mutation_refuses_second_word(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("compiler not available")
        source=(
            'static inline void execI_(\n'
            '\tu32 (INT_ATTR *fetch)(struct psxRegisters *r, '
            'const uintptr_t *luts, u32 pc),\n'
            '\tconst uintptr_t *memRLUT, psxRegisters *regs);\n'
            +native_opcode_witness()
        )
        instrumented=patch_interpreter(source)
        guest=expected_first_three_words()
        values=",".join("0x%08xu"%x for x in guest)
        c=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef struct { struct { unsigned char *psxM; } ptrs;
                 unsigned stop,branchSeen; } psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
#define INT_ATTR
''' +instrumented.split("static inline void execI_(",1)[1] if False else ""
        # Preserve exact native witness definition while removing its
        # interpreter prototype, which requires unrelated PCSX declarations.
        prefix=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct { struct { unsigned char *psxM; } ptrs;
                 unsigned stop,branchSeen; } psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
'''
        core=patch_interpreter(native_opcode_witness())
        c=prefix+core+r'''
int main(void){
    unsigned char ram[0x12000]={0};
    psxRegisters regs={0};
    static const u32 words[3]={WORDS};
    unsigned i,j;
    regs.ptrs.psxM=ram;
    for(i=0u;i<3u;i++)
      for(j=0u;j<4u;j++)
        ram[0x10000u+4u*i+j]=(unsigned char)(words[i]>>(8u*j));
    if(vh152_arm()!=0) return 1;
    vh153_arm_second_word_mutation();
    if(!vh152_before_dispatch(&regs,0x80010000u,words[0])) return 2;
    if(vh152_matched_count()!=1u || vh152_faulted()!=0u) return 3;
    if(ram[0x10004u]!=(unsigned char)((words[1]&0xffu)^1u)) return 4;
    if(vh152_before_dispatch(&regs,0x80010004u,words[1]^1u)) return 5;
    if(vh152_matched_count()!=1u || !vh152_faulted() ||
       !regs.stop || !regs.branchSeen) return 6;
    if(vh152_before_dispatch(&regs,0x80010008u,words[2])) return 7;
    vh152_disarm();
    puts("VH153_NATIVE_SECOND_WORD_COMPILED_PASS first_accepted=1 second_refused=1 latched=1");
    return 0;
}
'''.replace("WORDS",values)
        with tempfile.TemporaryDirectory(prefix="vh153-native-") as t:
            td=Path(t)
            src=td/"native.c"
            exe=td/"native"
            src.write_text(c)
            compile=subprocess.run(
                [cc,"-std=c99","-Wall","-Wextra","-Werror","-pedantic",
                 str(src),"-o",str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(compile.returncode,0,compile.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("VH153_NATIVE_SECOND_WORD_COMPILED_PASS",run.stdout)

    def test_c_source_guard_is_unique_and_reapplication_refused(self):
        src=native_opcode_witness()
        changed=patch_interpreter(src)
        self.assertIn("vh153_arm_second_word_mutation",changed)
        self.assertIn("[0x10004u]^=1u;",changed)
        self.assertIn("vh152_matches==1u",changed)
        with self.assertRaises(ValueError):
            patch_interpreter(changed)

    def test_frontend_is_strictly_synthetic_only(self):
        fixture=(
            "\tint vh152_mutate_post_verify = 0;\n"
            '\t\telse if (!strcmp(argv[i], "--vh152-mutate-post-verify"))\n'
            "    if(vh152_mutate_post_verify &&\n"
            "            if(vh152_mutate_post_verify)\n"
            "                ((unsigned char *)psxRegs.ptrs.psxM)[0x10000u]^=1u;\n"
            "            if(vh152_mutate_post_verify){\n"
            "                if(!faulted || witnessed!=0u){\n"
        )
        result=patch_frontend(fixture)
        self.assertIn("VH153_INVALID_MODE_REFUSED",result)
        self.assertIn("VH153_NATIVE_SECOND_WORD_REFUSED",result)
        self.assertIn("witnessed!=1u || vh150_steps()!=2u",result)
        self.assertIn("vh153_arm_second_word_mutation();",result)
        self.assertIn("vh152_mutate_post_verify))",result)
        with self.assertRaises(ValueError):
            patch_frontend(result)

    def test_full_matrix_wires_second_opcode_mutation(self):
        full=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        split=(ROOT/".github/workflows/map02-v153-second-instruction-mutation.yml").read_text()
        for marker in (
            "apply_map02_v153_second_instruction_mutation",
            "VH153_NATIVE_SECOND_WORD_REFUSED",
            "--vh153-mutate-second-word",
            "matched=1 attempted=2 original_retail=0",
        ):
            self.assertIn(marker,full)
        self.assertIn("test_map02_v153_second_instruction_mutation.py",split)


if __name__=="__main__":
    unittest.main()
