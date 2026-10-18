#!/usr/bin/env python3
"""v150 native guard source and compiled synthetic CPU safety regressions."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.apply_map02_v150_native_instruction_budget import (
    NATIVE_GUARD,patch_interpreter,patch_frontend,
)
from tools.make_map02_v129_four_vblank_exe import build


class NativeBoundedMipsInstructions(unittest.TestCase):
    def test_compiled_c_native_guard_ends_before_fourth_instruction(self):
        cc=os.environ.get("CC","cc")
        if shutil.which(cc) is None:
            self.skipTest("C compiler unavailable")
        program=r"""
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct { unsigned stop,branchSeen; } psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE
""" + NATIVE_GUARD + r"""
int main(void) {
    psxRegisters regs={0};
    unsigned writes=0, i;
    if(vh150_arm(0x80010000u,0x80012000u,3u)!=0) return 1;
    for(i=0;i<4u;i++) {
        if(!vh150_before(&regs,0x80010000u+4u*i)) break;
        writes++;
    }
    if(writes!=3u || i!=3u || vh150_steps()!=3u ||
       vh150_stop_reason()!=1u || !regs.stop || !regs.branchSeen)
        return 2;
    if(vh150_before(&regs,0x8001000cu)) return 11; /* latched stop */
    vh150_disarm();
    regs.stop=0; regs.branchSeen=0;
    if(vh150_arm(0x80010000u,0x80012000u,4u)!=0) return 3;
    if(!vh150_before(&regs,0x80010000u)) return 4;
    if(vh150_before(&regs,0x1f801810u)) return 5;
    if(vh150_steps()!=1u || vh150_stop_reason()!=2u ||
       !regs.stop || !regs.branchSeen) return 6;
    vh150_disarm();
    if(vh150_arm(0x80010000u,0x80012000u,0u)==0 ||
       vh150_arm(0x80010000u,0x80012000u,257u)==0 ||
       vh150_arm(0x80010002u,0x80012000u,3u)==0 ||
       vh150_arm(0x80012000u,0x80010000u,3u)==0) return 7;
    if(vh150_arm(0x80010000u,0x80012000u,1u)!=0) return 8;
    if(vh150_arm(0x80010000u,0x80012000u,1u)==0) return 9;
    vh150_disarm();
    if(!vh150_before(&regs,0xffffffffu)) return 10;
    puts("VH150_COMPILED_NATIVE_GATE_PASS steps=3 denied_fourth=1"
         " invalid_pc_refused=1 invalid_quota_refused=1");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="vh150-native-") as t:
            src=Path(t)/"gate.c"
            binary=Path(t)/"gate"
            src.write_text(program)
            build_run=subprocess.run(
                [cc,"-std=c99","-Wall","-Wextra","-Werror","-pedantic",
                 str(src),"-o",str(binary)],
                capture_output=True,text=True,timeout=30,check=False)
            self.assertEqual(build_run.returncode,0,build_run.stderr)
            run=subprocess.run([str(binary)],capture_output=True,
                               text=True,timeout=10,check=False)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(run.stdout.strip(),
                "VH150_COMPILED_NATIVE_GATE_PASS steps=3 denied_fourth=1"
                " invalid_pc_refused=1 invalid_quota_refused=1")

    def test_guard_installed_on_both_real_interpreter_paths(self):
        decl=("static inline void execI_(\n"
              "\tu32 (INT_ATTR *fetch)(struct psxRegisters *r, "
              "const uintptr_t *luts, u32 pc),\n"
              "\tconst uintptr_t *memRLUT, psxRegisters *regs);")
        def body(fn):
            return ("static inline void "+fn+"(\n"
              "\tu32 (INT_ATTR *fetch)(struct psxRegisters *r, "
              "const uintptr_t *luts, u32 pc),\n"
              "\tconst uintptr_t *memRLUT, psxRegisters *regs)\n"
              "{\n\tu32 pc = regs->pc;\n\n"
              "\taddCycle(regs);\n"
              "\tregs->pc += 4;\n}\n")
        source=decl+"\n"+body("execI_")+body("execIbp")
        altered=patch_interpreter(source)
        self.assertEqual(altered.count("vh150_before(regs,pc)"),2)
        self.assertEqual(altered.count(NATIVE_GUARD),1)
        self.assertLess(altered.index("if(!vh150_before(regs,pc)) return;"),
                        altered.index("addCycle(regs);"))
        self.assertIn("regs->stop=1;",altered)
        self.assertIn("regs->branchSeen=1;",altered)
        with self.assertRaises(ValueError):
            patch_interpreter(altered)
        with self.assertRaises(ValueError):
            patch_interpreter(decl+"\n"+body("execI_"))

    def test_native_frontend_path_is_strictly_synthetic(self):
        example=('\tint vh147_generic_trace = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh147-bounded-mmio"))\n'
            '    if(vh129_vblank_mode>=0) {\n'
            '        /* Execute GPU setup as an original interpreted MIPS stage. */\n'
            '        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);\n')
        result=patch_frontend(example)
        self.assertIn("vh150_arm(0x80010000u,0x80012000u,3u)",result)
        self.assertIn("vh150_stop_reason()",result)
        self.assertIn("if(count!=3u || reason!=1u)",result)
        self.assertIn("vh150_bounded_instructions && vh129_vblank_mode!=0",result)
        self.assertIn("VH150_NATIVE_BOUNDED_INTERPRETER_PASS",result)
        self.assertIn("original_retail=0",result)
        self.assertLess(result.index("vh150_arm("),
                        result.index("psxCpu->ExecuteBlock"))
        with self.assertRaises(ValueError):
            patch_frontend(result)

    def test_approved_fixture_is_only_the_source_authored_v129_exe(self):
        raw,*_=build()
        self.assertEqual(raw[:8],b"PS-X EXE")
        self.assertEqual(raw[0x4c:0x54],b"VH129SY!")
        self.assertEqual(len(raw)-2048,8192)
        self.assertNotIn("SLUS_004.47",NATIVE_GUARD)
        self.assertNotIn("original_mips_instruction_word",NATIVE_GUARD)

    def test_existing_v149_and_native_v147_scope_remain(self):
        wf=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v150-native-budget.yml").read_text()
        for expected in (
            "apply_map02_v150_native_instruction_budget",
            "VH150_NATIVE_BOUNDED_INTERPRETER_PASS",
            "VH147_NATIVE_BOUNDED_MMIO_PASS",
            "for mode in 04 13 22 31 40; do",
        ):
            self.assertIn(expected,wf)
        for expected in (
            "test_map02_v150_native_instruction_budget.py",
            "test_map02_v149_bounded_guest.py",
            "no_retail_game_files=1",
        ):
            self.assertIn(expected,isolated)


if __name__=="__main__":
    unittest.main()
