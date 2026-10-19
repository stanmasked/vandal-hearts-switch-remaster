#!/usr/bin/env python3
"""v182: refuse native 32-bit guest RAM MIPS LW/SW case-identity confusion.

The four v181 valid self-authored signed variants must NEVER be accepted
under the other three v181 source-authored opcode/PC/address expectations.
Tests all 12 wrong case pairings. Positive native validation remains v181.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from struct import unpack_from

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from tools.apply_map02_v181_word_ram_opcodes import CASES, make_variants, witness
from tools.make_map02_v179_nongpu_mips_exes import originals
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START

def wrong_pairs():
    return tuple((actual,expected) for actual in range(len(CASES))
                 for expected in range(len(CASES)) if actual != expected)

class V182FailClosedWordRAMIdentities(unittest.TestCase):
    def test_exactly_12_unique_cross_case_mismatches(self):
        cases=wrong_pairs()
        self.assertEqual(len(CASES),4)
        self.assertEqual(len(cases),12)
        self.assertEqual(len(set(cases)),12)
        self.assertEqual({(i,j) for i in range(4) for j in range(4) if i!=j},
                         set(cases))
        self.assertEqual(tuple(c[0] for c in CASES),
                         ("LW_RAM0","LW_RAM4","SW_RAM0","SW_RAM4"))
        words=tuple(c[1] for c in CASES)
        self.assertEqual(words,(0x8c000000,0x8c000004,0xac000000,0xac000004))
        self.assertEqual(len(set(words)),4)
        for actual,expected in cases:
            self.assertNotEqual(words[actual],words[expected])

    def test_each_valid_signed_image_has_exactly_one_distinct_word(self):
        original,index=originals()
        _,_,_,wait_pc,ops=build()
        self.assertEqual(index,(wait_pc-START)//4)
        self.assertEqual(ops[index:index+512],(0,)*512)
        offset=2048+index*4
        variants=make_variants()
        self.assertEqual(len(variants),4)
        for actual,(name,word,ram_addr,writing) in enumerate(CASES):
            blob=variants[name]
            self.assertEqual(blob[:offset],original[:offset])
            self.assertEqual(blob[offset+4:],original[offset+4:])
            self.assertEqual(unpack_from("<I",blob,offset)[0],word)
            for candidate in range(4):
                if candidate!=actual:
                    self.assertNotEqual(word,CASES[candidate][1])
            self.assertEqual(ram_addr%4,0)
            self.assertIn(writing,(0,1))

    def test_native_source_binds_code_site_and_exact_memory_address(self):
        c_source=witness()
        for token in ("regs->code!=vh181_expected_word[vh181_case]",
                      "regs->pc!=", "vh181_expected_addr[vh181_case]==physical",
                      "vh181_expected_write[vh181_case]==writing",
                      "vh181_seen++", "vh181_disarm"):
            self.assertIn(token,c_source)
        for _,opcode,_,_ in CASES:
            self.assertIn(f"0x{opcode:08x}u",c_source)
        self.assertNotIn("GPUwriteData(",c_source)
        self.assertNotIn("psxRegs.cycle=",c_source)

    def test_compiled_native_memory_observer_rejects_all_twelve_wrong_labels(self):
        """Real C callbacks: 12 mismatches ignored, 4 matching opcodes accepted."""
        import os
        import shutil
        import subprocess
        import tempfile
        sys.path.insert(0,str(ROOT/"tests"))
        from test_map02_v181_word_ram_opcodes import full_memory
        compiler=os.environ.get("CC","cc")
        if not shutil.which(compiler):
            self.skipTest("no C compiler")
        _,_,_,wait_pc,_=build()
        source = r"""
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {u32 pc;u32 code;} psxRegisters;
#define VH_MAP02_V66_PCSX_PROBE 1
static void vh138_pc_observe(psxRegisters *r,u32 a,u32 v) {
 (void)r;(void)a;(void)v;
}
""" + full_memory() + f"""
static void touch(psxRegisters *r,unsigned actual,unsigned wrong_address) {{
    static const u32 addresses[4]={{0u,4u,0u,4u}};
    u32 address=addresses[actual];
    if(wrong_address)address^=4u;
    if(actual<2u)(void)psxMemRead32(r,address);
    else psxMemWrite32(r,address,0u);
}}
int main(void) {{
    static const u32 words[4]={{0x8c000000u,0x8c000004u,0xac000000u,0xac000004u}};
    psxRegisters r={{0}};
    unsigned wrong=0u,correct=0u;
    for(unsigned actual=0u;actual<4u;actual++)
      for(unsigned expected=0u;expected<4u;expected++) {{
        if(vh173_arm_wait_quiet(0u)!=0 ||
           vh174_arm_wait_read(0u)!=0 ||
           vh175_arm_read_ports(0u)!=0 ||
           vh176_arm_narrow(0u)!=0 ||
           vh181_arm(expected,0u)!=0)return 1;
        r.pc={wait_pc+4}u;
        r.code=words[actual];
        touch(&r,actual,0u);
        if(vh181_count()!=(unsigned)(actual==expected) ||
           vh181_faults()!=0u)return 2;
        if(actual==expected)correct++;
        else wrong++;
        if(vh181_disarm(expected,0u)!=0 ||
           vh176_disarm_narrow(0u)!=0 ||
           vh175_disarm_read_ports(0u)!=0 ||
           vh174_disarm_wait_read(0u)!=0 ||
           vh173_disarm_wait_quiet(0u)!=0)return 3;
      }}
    if(wrong!=12u || correct!=4u)return 4;
    /* A valid opcode alone must not bypass PC or exact address checks. */
    for(unsigned kind=0u;kind<4u;kind++) {{
        if(vh173_arm_wait_quiet(0u)!=0 ||
           vh174_arm_wait_read(0u)!=0 ||
           vh175_arm_read_ports(0u)!=0 ||
           vh176_arm_narrow(0u)!=0 ||
           vh181_arm(kind,0u)!=0)return 5;
        r.code=words[kind];
        r.pc={wait_pc+8}u;touch(&r,kind,0u);
        if(vh181_count()!=0u || vh181_faults()!=0u)return 6;
        r.pc={wait_pc+4}u;touch(&r,kind,1u);
        /* Wrong RAM address must be reported as an explicit bad event. */
        if(vh181_count()!=0u || vh181_faults()!=1u)return 7;
        touch(&r,kind,0u);
        if(vh181_count()!=1u || vh181_faults()!=1u ||
           vh176_narrow_total()!=0u ||
           vh173_wait_mmio_faults()!=0u)return 8;
        if(vh181_disarm(kind,0u)!=0 ||
           vh176_disarm_narrow(0u)!=0 ||
           vh175_disarm_read_ports(0u)!=0 ||
           vh174_disarm_wait_read(0u)!=0 ||
           vh173_disarm_wait_quiet(0u)!=0)return 8;
    }}
    /* Correct opcode, PC and address cannot excuse incorrect direction. */
    for(unsigned kind=0u;kind<4u;kind++) {{
        static const u32 addresses[4]={{0u,4u,0u,4u}};
        if(vh173_arm_wait_quiet(0u)!=0 ||
           vh174_arm_wait_read(0u)!=0 ||
           vh175_arm_read_ports(0u)!=0 ||
           vh176_arm_narrow(0u)!=0 ||
           vh181_arm(kind,0u)!=0)return 9;
        r.code=words[kind];
        r.pc={wait_pc+4}u;
        if(kind<2u)psxMemWrite32(&r,addresses[kind],0u);
        else (void)psxMemRead32(&r,addresses[kind]);
        if(vh181_count()!=0u || vh181_faults()!=1u ||
           vh176_narrow_total()!=0u ||
           vh173_wait_mmio_faults()!=0u)return 10;
        if(vh181_disarm(kind,0u)!=0 ||
           vh176_disarm_narrow(0u)!=0 ||
           vh175_disarm_read_ports(0u)!=0 ||
           vh174_disarm_wait_read(0u)!=0 ||
           vh173_disarm_wait_quiet(0u)!=0)return 11;
    }}
    puts("VH182_COMPILED_WRONG_OPCODE_IDENTITY_PASS wrong_pairs=12 correct_pairs=4 wrong_pc_refused=4 wrong_ram_address_refused=4 wrong_direction_refused=4 original_retail=0");
    return 0;
}}
"""
        with tempfile.TemporaryDirectory(prefix="vh182-compiled-wrong-id-") as directory:
            src=Path(directory)/"witness.c"
            exe=Path(directory)/"witness"
            src.write_text(source)
            compile_run=subprocess.run(
                [compiler,"-std=c99","-Wall","-Wextra","-Werror","-pedantic",
                 str(src),"-o",str(exe)],
                capture_output=True,text=True,timeout=40
            )
            self.assertEqual(compile_run.returncode,0,compile_run.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=12)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn("VH182_COMPILED_WRONG_OPCODE_IDENTITY_PASS",result.stdout)
            self.assertIn("wrong_pairs=12 correct_pairs=4 wrong_pc_refused=4 wrong_ram_address_refused=4 wrong_direction_refused=4 original_retail=0",result.stdout)

    def test_native_ci_proves_all_wrong_pairings_have_exit_84(self):
        main=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        independent=(ROOT/".github/workflows/map02-v182-lw-sw-identity-mismatch.yml").read_text()
        for required in (
            "test_map02_v182_lw_sw_identity_mismatch.py",
            "V181_LW_RAM0.EXE",
            "V181_LW_RAM4.EXE",
            "V181_SW_RAM0.EXE",
            "V181_SW_RAM4.EXE",
            "VH181_NATIVE_WORD_UNOBSERVED_REFUSED",
            "VH181_NATIVE_GUEST_WORD_RAM_PASS",
            "VH182_NATIVE_GUEST_OPCODE_IDENTITY_REFUSED_PASS",
            'test "$rc" -eq 84',
            "if test \"$actual\" -eq \"$expected\"; then",
            "--vh181-nongpu-word-",
            "12 mismatches",
        ):self.assertIn(required,main)
        self.assertIn("test_map02_v181_word_ram_opcodes.py",independent)
        self.assertIn("original_retail_executed=0",independent)

if __name__=="__main__":
    unittest.main()
