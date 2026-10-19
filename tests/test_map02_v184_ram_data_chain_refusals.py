#!/usr/bin/env python3
"""MAP02 v184: independent RAM computed-value failure gate for 3 late mutations."""
from __future__ import annotations
from pathlib import Path
from struct import unpack_from
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))
from tools.make_map02_v184_ram_chain_negatives import MUTATIONS,PATCHES,make_variants,write_private
from tools.apply_map02_v183_native_ram_values import VALUE,TRANSFORMED,SEED1,signed_sequence
from tools.make_map02_v78_vblank_mips_exe import build
from tools.make_map02_v70_synthetic_psx_exe import START
from test_map02_v183_native_ram_values import guest_memory_result
from tools.apply_map02_v183_native_ram_values import RAM_ADDRESS

class V184RAMComputationFailClosed(unittest.TestCase):
    def test_distinct_guest_one_opcode_mutations(self):
        image,_,_,wait_pc,ops=build()
        index=(wait_pc-START)//4
        offset=2048+4*index
        expected=signed_sequence()
        self.assertEqual(tuple(ops[index:index+512]),(0,)*512)
        self.assertEqual(MUTATIONS,("MISSING_XORI","MISSING_FINAL_SW","WRONG_LW_ADDRESS"))
        self.assertEqual([p[0] for p in PATCHES],[7,8,5])
        self.assertEqual(len(set(PATCHES)),3)
        variants=make_variants()
        self.assertEqual(tuple(variants),MUTATIONS)
        for label,(at,opcode) in zip(MUTATIONS,PATCHES):
            actual=variants[label]
            self.assertEqual(len(actual),len(image))
            self.assertEqual(actual[:offset],image[:offset])
            self.assertEqual(actual[offset+36:],image[offset+36:])
            words=[unpack_from("<I",actual,offset+4*i)[0] for i in range(9)]
            desired=list(expected);desired[at]=opcode
            self.assertEqual(words,desired)
            self.assertEqual(actual[0x4c:0x54],b"VH78SYN!")

    def test_all_three_mutations_preserve_first_word_but_fail_second(self):
        expected=(VALUE,TRANSFORMED)
        self.assertEqual(
            tuple(guest_memory_result(signed_sequence())[addr] for addr in
                  (RAM_ADDRESS,RAM_ADDRESS+4)),expected
        )
        expected_second={
            "MISSING_XORI":VALUE,
            "MISSING_FINAL_SW":SEED1,
            "WRONG_LW_ADDRESS":SEED1 ^ 0xffff,
        }
        for label,(at,word) in zip(MUTATIONS,PATCHES):
            seq=list(signed_sequence());seq[at]=word
            ram=guest_memory_result(seq)
            self.assertEqual(ram[RAM_ADDRESS],VALUE)
            self.assertEqual(ram[RAM_ADDRESS+4],expected_second[label])
            self.assertNotEqual(ram[RAM_ADDRESS+4],TRANSFORMED)
        with tempfile.TemporaryDirectory(prefix="vh184-private-") as directory:
            folder=Path(directory)
            self.assertEqual(write_private(folder),3)
            for name in MUTATIONS:
                item=folder/("V184_RAM_"+name+".EXE")
                self.assertEqual(item.stat().st_mode & 0o777,0o600)
            with self.assertRaises(ValueError):write_private(folder)

    def test_native_pin_has_3_explicit_cases_all_negative_code_85(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone=(ROOT/".github/workflows/map02-v184-ram-data-chain-refusals.yml").read_text()
        tokens=(
            "make_map02_v184_ram_chain_negatives",
            "test_map02_v184_ram_data_chain_refusals.py",
            "MISSING_XORI MISSING_FINAL_SW WRONG_LW_ADDRESS",
            "V184_RAM_$kind.EXE",
            "--vh183-guest-ram-values",
            "VH183_NATIVE_RAM_VALUE_REFUSED phase=0 first_ok=1 derived_ok=0",
            "VH184_NATIVE_GUEST_RAM_CHAIN_REFUSALS_PASS",
            'test "$rc" -eq 85',
            "VH183_NATIVE_GUEST_RAM_VALUES_PASS",
        )
        for token in tokens:self.assertIn(token,workflow)
        self.assertIn("test_map02_v183_native_ram_values.py",standalone)
        self.assertIn("original_retail_executed=0",standalone)

if __name__=="__main__":
    unittest.main()
