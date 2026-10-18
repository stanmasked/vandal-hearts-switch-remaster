#!/usr/bin/env python3
"""v152 fetched-opcode + guest RAM witness unit/native C regressions."""
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
    expected_first_three_words,native_opcode_witness,
    patch_interpreter,patch_frontend,
)


class NativeFetchedOpcodeWitness(unittest.TestCase):
    def test_first_three_words_are_source_derived(self):
        words=expected_first_three_words()
        self.assertEqual(len(words),3)
        self.assertTrue(all(isinstance(w,int) and 0<w<0x100000000 for w in words))
        src=native_opcode_witness()
        self.assertEqual(src.count("static const u32 vh152_words[3]"),1)
        for word in words:
            self.assertIn("0x%08xu"%word,src)
        self.assertNotIn("V152_SOURCE_WORDS",src)

    def test_both_native_interpreter_opcodes_are_checked_before_dispatch(self):
        opcode=("\tregs->code = fetch(regs, memRLUT, pc);\n"
                "\tpsxBSC[regs->code >> 26](regs, regs->code);")
        prior=("static inline void execI_(\n"
               "\tu32 (INT_ATTR *fetch)(struct psxRegisters *r, "
               "const uintptr_t *luts, u32 pc),\n"
               "\tconst uintptr_t *memRLUT, psxRegisters *regs);\n"
               "static inline void execIbp(\n"
               "\tconst uintptr_t *memRLUT, psxRegisters *regs);\n"
               +opcode+"\n"+opcode)
        patched=patch_interpreter(prior)
        self.assertEqual(patched.count(
            "if(!vh152_before_dispatch(regs,pc,regs->code)) return;"),2)
        self.assertEqual(patched.count("psxBSC[regs->code >> 26]"),2)
        self.assertEqual(patched.count("vh152_before_dispatch("),3)
        self.assertNotIn("original_retail_MIPS",patched)
        with self.assertRaises(ValueError):
            patch_interpreter(patched)
        with self.assertRaises(ValueError):
            patch_interpreter(prior.replace(opcode,"",1))

    def test_frontend_requires_synthetic_mode_and_post_sha_tamper(self):
        fixture=(
            "\tint vh150_bounded_instructions = 0;\n"
            '\t\telse if (!strcmp(argv[i], "--vh150-bounded-instructions"))\n'
            "    if(vh150_bounded_instructions && vh129_vblank_mode!=0){\n"
            "        if(vh150_bounded_instructions){\n"
            "            if(!vh151_verify_payload(guest_ram)) return 55;\n"
            "            if(vh150_arm(0x80010000u,0x80012000u,3u)!=0){\n"
            "        if(vh150_bounded_instructions){\n"
            "            unsigned count=vh150_steps();"
        )
        result=patch_frontend(fixture)
        self.assertIn("VH152_INVALID_MODE_REFUSED",result)
        self.assertIn("VH152_NATIVE_FETCH_TAMPER_REFUSED",result)
        self.assertIn("vh152_mutate_post_verify",result)
        self.assertLess(result.index("vh151_verify_payload("),
                        result.index("if(vh152_arm()"))
        self.assertLess(result.index("if(vh152_arm()"),
                        result.index("psxRegs.ptrs.psxM)[0x10000u]^=1u"))
        self.assertLess(result.index("psxRegs.ptrs.psxM)[0x10000u]^=1u"),
                        result.index("if(vh150_arm("))
        self.assertIn("witnessed!=0u",result)
        with self.assertRaises(ValueError):
            patch_frontend(result)

    def test_compiled_native_witness_rejects_ram_and_fetch_mutations(self):
        cc=os.environ.get("CC","cc")
        if shutil.which(cc) is None:
            self.skipTest("C compiler not installed")
        words=expected_first_three_words()
        values=",".join("0x%08xu"%w for w in words)
        csource=r'''
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {
    struct { unsigned char *psxM; } ptrs;
    unsigned stop,branchSeen;
} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
''' + native_opcode_witness()+r'''
int main(void) {
    unsigned char ram[0x12000]={0};
    psxRegisters regs={0};
    static const u32 sample[3]={SOURCE_WORDS};
    unsigned i,j;
    regs.ptrs.psxM=ram;
    for(i=0u;i<3u;i++)
        for(j=0u;j<4u;j++)
            ram[0x10000u+4u*i+j]=(unsigned char)(sample[i]>>(8u*j));

    if(vh152_arm()!=0) return 2;
    for(i=0u;i<3u;i++)
        if(!vh152_before_dispatch(&regs,0x80010000u+i*4u,sample[i]))
            return 3;
    if(vh152_matched_count()!=3u || vh152_faulted()!=0u) return 4;
    vh152_disarm();

    /* Simulate a post-SHA TOCTOU mutation of exactly one guest RAM byte.
     * Cached/fetched word still appears unchanged: RAM check must catch it. */
    ram[0x10000u]^=1u;
    if(vh152_arm()!=0) return 5;
    if(vh152_before_dispatch(&regs,0x80010000u,sample[0])) return 6;
    if(!vh152_faulted() || vh152_matched_count()!=0u ||
       !regs.stop || !regs.branchSeen) return 7;
    if(vh152_before_dispatch(&regs,0x80010000u,sample[0])) return 8;
    vh152_disarm();

    /* Separate opcode fetch corruption with intact RAM. */
    ram[0x10000u]^=1u;
    regs.stop=regs.branchSeen=0u;
    if(vh152_arm()!=0) return 9;
    if(vh152_before_dispatch(&regs,0x80010000u,sample[0]^1u))
        return 10;
    if(!vh152_faulted() || vh152_matched_count()!=0u) return 11;
    vh152_disarm();
    if(!vh152_before_dispatch(&regs,0xffffffffu,0u)) return 12;
    puts("VH152_COMPILED_FETCH_WITNESS_PASS matched=3 ram_mutation_refused=1 fetched_mutation_refused=1 latched=1");
    return 0;
}
'''.replace("SOURCE_WORDS",values)
        with tempfile.TemporaryDirectory(prefix="vh152-native-") as td:
            root=Path(td)
            src=root/"native.c"
            exe=root/"native"
            src.write_text(csource)
            build=subprocess.run([cc,"-std=c99","-Wall","-Wextra",
                        "-Werror","-pedantic",str(src),"-o",str(exe)],
                        capture_output=True,text=True,timeout=30)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(exe)],capture_output=True,
                               text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("VH152_COMPILED_FETCH_WITNESS_PASS",run.stdout)

    def test_full_pinned_pcsx_includes_post_sha_guest_mutation(self):
        full=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v152-fetch-opcode-witness.yml").read_text()
        for marker in (
            "apply_map02_v152_fetch_opcode_witness",
            "VH152_NATIVE_FETCH_TAMPER_REFUSED",
            "--vh152-mutate-post-verify",
            "VH150_NATIVE_BOUNDED_INTERPRETER_PASS",
        ):
            self.assertIn(marker,full)
        self.assertIn("test_map02_v152_fetch_opcode_witness.py",isolated)


if __name__=="__main__":
    unittest.main()
