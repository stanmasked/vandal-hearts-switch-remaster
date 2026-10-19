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
