#!/usr/bin/env python3
"""Prevent recurrence of the GCC/Clang v129 fifth-mode C bounds defect."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.check_map02_v130_native_bounds import (
    Refused,SHAPES,C_CHECKS,extract_declarations,make_c,
    negative_cases,mutate_table,replace_exact
)

class NativeFiveModeCompilerGuards(unittest.TestCase):
    def test_native_generated_oracle_declares_five_real_rows(self):
        tables=extract_declarations()
        self.assertEqual(set(tables),set(SHAPES))
        for name,shape in SHAPES.items():
            self.assertIn(name+shape,tables[name])
            self.assertIn("static const unsigned",tables[name])
        self.assertIn("{4u,0u}",tables["vh129_boundary_targets"])
        self.assertIn("{2u,0u,2u,0u,0u}",
                      tables["vh129_adjacent_histograms"])

    def test_seven_negative_mutations_are_complete_and_isolated(self):
        good=make_c(extract_declarations())
        variants=negative_cases(good)
        self.assertEqual(len(variants),7)
        self.assertEqual(
            {name for name,(_,type_) in variants.items() if type_=="compile"},
            {"four_boundary_rows","four_histogram_rows","four_return_rows"})
        self.assertEqual(
            {name for name,(_,type_) in variants.items() if type_=="runtime"},
            {"wrong_fifth_boundary","wrong_histogram",
             "wrong_expected_total","wrong_four_back_return"})
        self.assertEqual(len(set(src for src,_ in variants.values())),7)
        for src,_ in variants.values():
            self.assertIn("expected_splits[5][2]",src)
            self.assertIn("expected_adjacent[5][5]",src)
            self.assertIn("VH130_NATIVE_VBLANK_TABLE_BOUNDS_PASS",src)
            self.assertNotEqual(src,good)

    def test_wrong_declarations_refuse_early(self):
        source=(ROOT/"tools/apply_map02_v129_pcsx_rearmed.py").read_text()
        self.assertIn('"vh129_boundary_targets[5][2]"',source)
        with self.assertRaises(Refused):
            extract_declarations("static const unsigned vh129_boundary_targets[4][2]={{0u,4u}};")
        with self.assertRaises(Refused):
            extract_declarations("")
        with self.assertRaises(Refused):
            make_c({})
        with self.assertRaises(Refused):
            replace_exact("hello","missing","wrong")
        with self.assertRaises(Refused):
            mutate_table(make_c(extract_declarations()),
                         "vh129_boundary_targets","not-present","wrong")

    def test_v129_emulator_native_witness_and_private_guard_preserved(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for token in (
            "python3 -m remaster.tools.check_map02_v130_native_bounds",
            "python3 -m unittest discover -s remaster/tests -p 'test_map02_v130_native_bounds.py' -v",
            "apply_map02_v129_pcsx_rearmed",
            "for mode in 04 13 22 31 40; do",
            '"--vh129-vblank-$mode"',
            "VH129_REAL_VBLANK_PROFILES_PASS mode=",
            "sha256sum -c proof/private/native.sha256",
            "summarize_map02_v129_four_vblank_profiles",
        ):
            with self.subTest(token=token):
                self.assertIn(token,workflow)

    def test_native_guards_and_sanitizer_are_mandatory(self):
        for token in (
            "_Static_assert(sizeof(vh129_boundary_targets)",
            "_Static_assert(sizeof(vh129_adjacent_histograms)",
            "_Static_assert(sizeof(return_gap)",
            "expected_splits[5][2]",
            "expected_adjacent[5][5]",
            "return 11;",
            "return 12;",
            "return 13;",
        ):
            self.assertIn(token,C_CHECKS)
        script=(ROOT/"tools/check_map02_v130_native_bounds.py").read_text()
        for token in ("-Werror","-fsanitize=undefined,bounds",
                      "if compiled:",
                      "result.returncode==0",
                      "TemporaryDirectory(", "compile_refusals=3",
                      "runtime_refusals=4"):
            self.assertIn(token,script)

if __name__=="__main__":
    unittest.main()
