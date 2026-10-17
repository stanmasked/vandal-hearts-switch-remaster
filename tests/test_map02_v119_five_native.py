#!/usr/bin/env python3
"""Native exact 24-value A-B-C-D-A returns with bounded four-state lookback."""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v115_sample_value_identity import native,note,Metrics
from test_map02_v117_aba_native import Triplets
from test_map02_v118_four_native import Quads


class Quints(ctypes.Structure):
    _fields_=[
        ("consecutive_quintuplets",ctypes.c_uint32),
        ("same_as_previous",ctypes.c_uint32*5),
        ("returned_to_two_back",ctypes.c_uint32*5),
        ("returned_to_three_back",ctypes.c_uint32*5),
        ("returned_to_four_back",ctypes.c_uint32*5),
        ("different_from_all_four",ctypes.c_uint32*5),
    ]


class NativeFiveHandlerReturns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("C compiler not installed")
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        folder=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v115_sample_identity.h",
                        folder/"vh115_sample_identity.h")
        output=folder/"libvh119.so"
        proc=subprocess.run([
            cc,"-std=c11","-Wall","-Wextra","-Werror",
            "-shared","-fPIC","-I",str(folder),
            str(ROOT/"tools/map02_v115_sample_identity.c"),
            "-o",str(output)],text=True,capture_output=True)
        if proc.returncode:raise AssertionError(proc.stderr)
        cls.lib=native(output)
        cls.lib.vh118_get_quadruplet_metrics.argtypes=[ctypes.POINTER(Quads)]
        cls.lib.vh118_get_quadruplet_metrics.restype=ctypes.c_int
        cls.lib.vh119_get_quintuplet_metrics.argtypes=[ctypes.POINTER(Quints)]
        cls.lib.vh119_get_quintuplet_metrics.restype=ctypes.c_int

    def setUp(self):
        self.lib.vh115_reset()
        self.lib.vh115_enable(1)

    def record(self,number):
        note(self.lib,[number]*24,1)

    def report(self):
        out=Quints()
        self.assertEqual(self.lib.vh119_get_quintuplet_metrics(ctypes.byref(out)),0)
        return out

    def test_abcda_true_return_to_four_back_after_three_other_states(self):
        for v in (0,1,2,3,0):self.record(v)
        m=self.report()
        self.assertEqual(m.consecutive_quintuplets,1)
        self.assertEqual(m.returned_to_four_back[0],1)
        self.assertEqual(sum(m.returned_to_three_back),0)

    def test_abcdb_recovers_three_back_with_recency_precedence(self):
        for v in (0,1,2,3,1):self.record(v)
        self.assertEqual(self.report().returned_to_three_back[0],1)

    def test_abcdc_recovers_two_back(self):
        for v in (0,1,2,3,2):self.record(v)
        self.assertEqual(self.report().returned_to_two_back[0],1)

    def test_abcdd_repeats_latest_value(self):
        for v in (0,1,2,3,3):self.record(v)
        self.assertEqual(self.report().same_as_previous[0],1)

    def test_abcde_differs_from_all_previous(self):
        for v in (0,1,2,3,4):self.record(v)
        self.assertEqual(self.report().different_from_all_four[0],1)

    def test_aaaaa_is_not_mislabelled_as_a_return(self):
        for _ in range(5):self.record(13)
        m=self.report()
        self.assertEqual(m.same_as_previous[0],1)
        self.assertEqual(sum(m.returned_to_four_back),0)

    def test_return_to_four_back_for_each_gap_from_zero_to_four(self):
        for gap in range(5):
            with self.subTest(gap=gap):
                self.lib.vh115_reset()
                self.lib.vh115_enable(1)
                for v in (0,1,2,3):self.record(v)
                for _ in range(gap):self.lib.vh115_vblank()
                self.record(0)
                self.assertEqual(list(self.report().returned_to_four_back),
                                 [int(i==gap) for i in range(5)])

    def test_overlapping_five_callback_windows_do_not_double_count(self):
        for v in (0,1,2,3,0,1):self.record(v)
        m=self.report()
        self.assertEqual(m.consecutive_quintuplets,2)
        self.assertEqual(m.returned_to_four_back[0],2)

    def test_less_than_five_handlers_yields_zero_quintuplets(self):
        for v in (0,1,2,0):self.record(v)
        self.assertEqual(self.report().consecutive_quintuplets,0)

    def test_secure_reset_erases_four_previous_sample_buffers(self):
        for v in (0xffff,3,7,11,0xffff):self.record(v)
        self.assertEqual(self.report().returned_to_four_back[0],1)
        self.lib.vh115_reset()
        self.assertEqual(self.lib.vh115_sample_cache_erased(),1)
        m=Quints()
        self.assertNotEqual(self.lib.vh119_get_quintuplet_metrics(ctypes.byref(m)),0)
        self.lib.vh115_enable(1)
        self.record(0)
        self.assertEqual(self.report().consecutive_quintuplets,0)

    def test_fifth_vblank_is_refused(self):
        for v in (0,1,2,3):self.record(v)
        for _ in range(5):self.lib.vh115_vblank()
        self.record(0)
        m=Quints()
        self.assertNotEqual(self.lib.vh119_get_quintuplet_metrics(ctypes.byref(m)),0)

    def test_legacy_v115_v118_native_abi_and_counters_intact(self):
        for v in (0,1,2,3,0):self.record(v)
        older=Metrics()
        four=Quads()
        self.assertEqual(self.lib.vh115_get_metrics(ctypes.byref(older)),0)
        self.assertEqual(self.lib.vh118_get_quadruplet_metrics(ctypes.byref(four)),0)
        self.assertEqual(older.handlers,5)
        self.assertEqual(four.consecutive_quadruplets,2)
        self.assertEqual(self.report().consecutive_quintuplets,1)
        self.assertEqual(ctypes.sizeof(Metrics),32)

    def test_bad_sample_delta_is_refused_with_no_report(self):
        for v in (0,1,2,3):self.record(v)
        note(self.lib,[0]*24,25)
        m=Quints()
        self.assertNotEqual(self.lib.vh119_get_quintuplet_metrics(ctypes.byref(m)),0)

    def test_pinned_full_emulator_uses_native_bounded_return_witness(self):
        text=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("apply_map02_v119_pcsx_rearmed",text)
        self.assertIn("VH119_QUINTUPLETS_PASS",text)
        self.assertIn("v119-quintuplet-summary.json",text)
        self.assertIn("path: proof/public/",text)


if __name__=="__main__":
    unittest.main()
