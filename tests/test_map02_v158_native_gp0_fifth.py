#!/usr/bin/env python3
"""v158: real fifth synthetic MIPS SW reaches PCSX GP0 MMIO exactly once."""
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
from tools.apply_map02_v155_four_instruction_native import patch_interpreter as v155
from tools.apply_map02_v156_register_checkpoints import patch_interpreter as v156
from tools.apply_map02_v157_t1_fourth_checkpoint import patch_interpreter as v157
from tools.apply_map02_v158_native_gp0_fifth import (
    five_source_words, gp0_observer_c, patch_memory, patch_interpreter,
    patch_frontend
)


def source_core():
    return patch_interpreter(v157(v156(v155(v154(v153(native_opcode_witness()))))))


class NativeSyntheticGp0Fifth(unittest.TestCase):
    def test_source_authored_fifth_is_sw_t1_zero_t0(self):
        words=five_source_words()
        self.assertEqual(len(words),5)
        self.assertEqual(words[4],0xad090000)
        self.assertEqual((words[4]>>21)&31,8)  # MIPS base register t0
        self.assertEqual((words[4]>>16)&31,9)  # source register t1
        code=source_core()
        self.assertIn("static const u32 vh152_words[5]",code)
        self.assertIn("vh158_five_enabled ? 5u :",code)
        self.assertIn("[0x10010u]^=1u;",code)
        self.assertIn("pc==0x80010010u",code)
        with self.assertRaises(ValueError):
            patch_interpreter(code)

    def test_memory_observer_tracks_real_psx_hw_path(self):
        fixture=(
            "void vh140_mmio_enable(unsigned mutate_expected) {\n"
            "  /* previous pinned native capture code */\n"
            "}\n"
            "    if(vh147_active) vh147_capture(regs,addr,value);\n"
        )
        patched=patch_memory(fixture)
        self.assertIn("static void vh158_capture_gp0(",patched)
        self.assertIn("vh158_gp0_active) vh158_capture_gp0(regs,addr,value)",patched)
        self.assertIn("regs->pc!=0x80010014u",patched)
        self.assertIn("regs->code!=0xad090000u",patched)
        with self.assertRaises(ValueError):
            patch_memory(patched)

    def test_compiled_c_positive_five_guest_sw_and_pre_dispatch_refusal(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("native C compiler unavailable")
        words=",".join("0x%08xu"%w for w in five_source_words())
        core=source_core()
        src=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {
    union { u32 r[34]; } GPR;
    u32 pc,code;
    unsigned stop,branchSeen;
    struct {unsigned char *psxM;} ptrs;
} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
'''+NATIVE_GUARD+core+gp0_observer_c()+r'''
static const u32 words[5]={SOURCE_WORDS};
static void reset_ram(unsigned char *ram) {
    unsigned i,j;
    for(i=0u;i<5u;i++)
      for(j=0u;j<4u;j++)
        ram[0x10000u+4u*i+j]=(unsigned char)(words[i]>>(j*8u));
}
static void simulate(psxRegisters *regs,u32 ins) {
    unsigned op=ins>>26u,rs=(ins>>21u)&31u,rt=(ins>>16u)&31u;
    if(op==15u) regs->GPR.r[rt]=(ins&0xffffu)<<16u;
    else if(op==13u) regs->GPR.r[rt]=regs->GPR.r[rs]|(ins&0xffffu);
    else if(op==0x2bu) {
        u32 address=regs->GPR.r[rs]+(int16_t)(ins&0xffffu);
        u32 value=regs->GPR.r[rt];
        regs->pc+=4u; /* PCSX interpreter advances PC before MIPS SW */
        regs->code=ins;
        vh158_capture_gp0(regs,address,value);
    }
}
int main(void){
    unsigned char ram[0x12000]={0};
    psxRegisters r={0};
    unsigned i;
    r.ptrs.psxM=ram;
    reset_ram(ram);

    /* Old four-word mode must reject fifth before native instruction. */
    if(vh152_arm()!=0 || vh155_enable_four()!=0) return 1;
    for(i=0u;i<4u;i++){
        if(!vh152_before_dispatch(&r,0x80010000u+i*4u,words[i])) return 2;
    }
    if(vh152_before_dispatch(&r,0x80010010u,words[4])) return 3;
    vh152_disarm();r.stop=r.branchSeen=0u;

    /* Five exact source opcodes, actual MMIO hook only for fifth SW. */
    r.GPR.r[8]=r.GPR.r[9]=0u;
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh156_arm_register_check(0)!=0 || vh158_enable_five()!=0 ||
       vh150_arm(0x80010000u,0x80012000u,5u)!=0) return 4;
    vh158_arm_gp0();
    for(i=0u;i<5u;i++){
        r.pc=0x80010000u+i*4u;
        if(!vh150_before(&r,r.pc) ||
           !vh152_before_dispatch(&r,r.pc,words[i])) return 5;
        simulate(&r,words[i]);
    }
    if(vh158_gp0_writes()!=1u || vh158_gp0_faults()!=0u ||
       vh152_matched_count()!=5u || vh152_faulted()!=0u) return 6;
    if(vh150_before(&r,0x80010014u) ||
       vh150_steps()!=5u || vh150_stop_reason()!=1u) return 7;
    vh158_disarm_gp0();vh152_disarm();vh150_disarm();
    r.stop=r.branchSeen=0u;
    r.GPR.r[8]=r.GPR.r[9]=0u;

    /* Exactly four words executed; fifth mutated in RAM and refused. */
    reset_ram(ram);
    if(vh152_arm()!=0 || vh155_enable_four()!=0 ||
       vh156_arm_register_check(0)!=0 || vh158_enable_five()!=0 ||
       vh150_arm(0x80010000u,0x80012000u,5u)!=0) return 8;
    vh158_arm_gp0();
    vh158_arm_fifth_mutation();
    for(i=0u;i<4u;i++){
        r.pc=0x80010000u+4u*i;
        if(!vh150_before(&r,r.pc) ||
           !vh152_before_dispatch(&r,r.pc,words[i])) return 9;
        simulate(&r,words[i]);
    }
    if(ram[0x10010u]!=(unsigned char)((words[4]&255u)^1u)) return 10;
    r.pc=0x80010010u;
    if(!vh150_before(&r,r.pc) ||
       vh152_before_dispatch(&r,r.pc,words[4]^1u)) return 11;
    if(vh158_gp0_writes()!=0u || vh158_gp0_faults()!=0u ||
       vh152_matched_count()!=4u || !vh152_faulted() ||
       vh150_steps()!=5u || vh150_stop_reason()!=0u ||
       !r.stop || !r.branchSeen) return 12;
    if(vh152_before_dispatch(&r,r.pc,words[4])) return 13;
    vh158_disarm_gp0();vh152_disarm();vh150_disarm();
    puts("VH158_COMPILED_NATIVE_GP0_PASS five=5 gp0_writes=1 fifth_refused=1 old_four_preserved=1 original_retail=0");
    return 0;
}
'''.replace("SOURCE_WORDS",words)
        with tempfile.TemporaryDirectory(prefix="vh158-gp0-") as td:
            p=Path(td)
            (p/"test.c").write_text(src)
            exe=p/"test"
            res=subprocess.run([cc,"-std=c99","-Wall","-Wextra","-Werror",
                "-pedantic",str(p/"test.c"),"-o",str(exe)],
                capture_output=True,text=True,timeout=35)
            self.assertEqual(res.returncode,0,res.stderr)
            done=subprocess.run([str(exe)],capture_output=True,
                                text=True,timeout=10)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertIn("VH158_COMPILED_NATIVE_GP0_PASS",done.stdout)

    def test_compiled_gp0_observer_rejects_wrong_address_data_pc_opcode(self):
        cc=os.environ.get("CC","cc")
        if not shutil.which(cc):
            self.skipTest("native C compiler unavailable")
        program=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct {
    u32 pc,code;
} psxRegisters;
'''+gp0_observer_c()+r'''
int main(void){
    psxRegisters r={0x80010014u,0xad090000u};
    unsigned i;
    static const u32 wrong_address[2]={0x1f801814u,0x1f80180cu};
    if(vh158_gp0_writes() || vh158_gp0_faults()) return 1;
    /* Inactive observer must never record any native caller event. */
    vh158_capture_gp0(&r,0x1f801810u,0xe3000000u);
    if(vh158_gp0_writes() || vh158_gp0_faults()) return 2;
    vh158_arm_gp0();
    vh158_capture_gp0(&r,0x1f801810u,0xe3000000u);
    if(vh158_gp0_writes()!=1u || vh158_gp0_faults()) return 3;
    /* An extra correct MMIO write must never be confused with one write. */
    vh158_capture_gp0(&r,0x1f801810u,0xe3000000u);
    if(vh158_gp0_writes()!=2u || vh158_gp0_faults()) return 4;
    vh158_arm_gp0();
    for(i=0u;i<2u;i++)
        vh158_capture_gp0(&r,wrong_address[i],0xe3000000u);
    if(vh158_gp0_writes()!=0u || vh158_gp0_faults()!=2u) return 5;
    vh158_arm_gp0();
    vh158_capture_gp0(&r,0x1f801810u,0xe3000001u);
    if(vh158_gp0_writes()!=0u || vh158_gp0_faults()!=1u) return 6;
    vh158_arm_gp0();
    r.pc=0x80010010u;
    vh158_capture_gp0(&r,0x1f801810u,0xe3000000u);
    if(vh158_gp0_writes()!=0u || vh158_gp0_faults()!=1u) return 7;
    vh158_arm_gp0();
    r.pc=0x80010014u; r.code=0xac090000u; /* wrong SW base t0 */
    vh158_capture_gp0(&r,0x1f801810u,0xe3000000u);
    if(vh158_gp0_writes()!=0u || vh158_gp0_faults()!=1u) return 8;
    vh158_disarm_gp0();
    vh158_capture_gp0(&r,0x1f801810u,0xe3000000u);
    if(vh158_gp0_writes()!=0u || vh158_gp0_faults()!=1u) return 9;
    puts("VH158_COMPILED_GP0_EXACT_MATCH_PASS valid=1 duplicate_detected=1 wrong_address=2 wrong_value=1 wrong_pc=1 wrong_opcode=1 inactive=1");
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="vh158-gp0-strict-") as td:
            p=Path(td)
            (p/"observer.c").write_text(program)
            exe=p/"observer"
            built=subprocess.run([cc,"-std=c99","-Wall","-Wextra","-Werror",
                                  "-pedantic",str(p/"observer.c"),"-o",str(exe)],
                                 capture_output=True,text=True,timeout=35)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(exe)],capture_output=True,
                                  text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn("VH158_COMPILED_GP0_EXACT_MATCH_PASS",result.stdout)

    def test_frontend_requires_strict_source_synthetic_mode(self):
        fixture=(
            "\tint vh157_corrupt_t1_fourth = 0;\n"
            '\t\telse if (!strcmp(argv[i], "--vh157-corrupt-t1-fourth"))\n'
            "    if(vh157_corrupt_t1_fourth &&\n"
            "                if(vh157_corrupt_t1_fourth)\n"
            "                    vh157_arm_t1_fourth();\n"
            "if(vh150_arm(0x80010000u,0x80012000u,\n"
            "                         vh155_four_instructions ? 4u : 3u)!=0){\n"
            "                if(vh156_verify_register_effects){\n"
            "                    if(vh157_corrupt_t1_fourth){"
        )
        changed=patch_frontend(fixture)
        self.assertIn("VH158_INVALID_MODE_REFUSED",changed)
        self.assertIn("VH158_NATIVE_GP0_FIFTH_PASS",changed)
        self.assertIn("VH158_NATIVE_FIFTH_OPCODE_REFUSED",changed)
        self.assertIn("vh158_five_instructions ? 5u :",changed)
        self.assertIn("vh158_gp0_writes();",changed)
        self.assertIn("psxRegs.GPR.r[8]!=0x1f801810u",changed)
        with self.assertRaises(ValueError):
            patch_frontend(changed)

    def test_pinned_native_workflow_runs_real_gp0_positive_and_negative(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        isolated=(ROOT/".github/workflows/map02-v158-native-gp0-fifth.yml").read_text()
        for marker in (
            "apply_map02_v158_native_gp0_fifth",
            "VH158_NATIVE_GP0_FIFTH_PASS",
            "VH158_NATIVE_FIFTH_OPCODE_REFUSED",
            "--vh158-five-instructions",
            "--vh158-mutate-fifth",
            "VH157_NATIVE_T1_FOURTH_REFUSED",
            "VH156_NATIVE_REGISTER_EFFECTS_PASS",
        ):
            self.assertIn(marker,native)
        self.assertIn("test_map02_v158_native_gp0_fifth.py",isolated)
        self.assertIn("original_retail_executed=0",isolated)


if __name__=="__main__":
    unittest.main()
