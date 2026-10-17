#!/usr/bin/env python3
"""Exact native 24-value A-B-A returns across up to four VBlank callbacks."""
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
from test_map02_v116_sample_gap_identity import GapMetrics


class Triplets(ctypes.Structure):
    _fields_=[
        ("consecutive_triplets",ctypes.c_uint32),
        ("same_as_previous",ctypes.c_uint32*5),
        ("returned_to_two_back",ctypes.c_uint32*5),
        ("different_from_both",ctypes.c_uint32*5),
    ]


class NativeAba(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        folder=Path(cls.temp.name)
        shutil.copyfile(ROOT/"tools/map02_v115_sample_identity.h",
                        folder/"vh115_sample_identity.h")
        output=folder/"libvh117.so"
        p=subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                          "-shared","-fPIC","-I",str(folder),
                          str(ROOT/"tools/map02_v115_sample_identity.c"),
                          "-o",str(output)],text=True,capture_output=True)
        if p.returncode:raise AssertionError(p.stderr)
        cls.lib=native(output)
        cls.lib.vh116_get_gap_metrics.argtypes=[ctypes.POINTER(GapMetrics)]
        cls.lib.vh116_get_gap_metrics.restype=ctypes.c_int
        cls.lib.vh117_get_triplet_metrics.argtypes=[ctypes.POINTER(Triplets)]
        cls.lib.vh117_get_triplet_metrics.restype=ctypes.c_int

    def setUp(self):
        self.lib.vh115_reset()
        self.lib.vh115_enable(1)

    def snap(self):
        m=Triplets()
        self.assertEqual(self.lib.vh117_get_triplet_metrics(ctypes.byref(m)),0)
        return m

    def test_exact_aba_recovery_after_actual_intermediate_change(self):
        a=[0]*24
        b=[0]*24
        b[7]=17
        note(self.lib,a,0)
        note(self.lib,b,1)
        note(self.lib,a,1)
        m=self.snap()
        self.assertEqual(m.consecutive_triplets,1)
        self.assertEqual(m.returned_to_two_back[0],1)
        self.assertEqual(sum(m.same_as_previous),0)
        self.assertEqual(sum(m.different_from_both),0)

    def test_abb_does_not_count_as_return(self):
        a=[0]*24
        b=[7]*24
        note(self.lib,a,0)
        note(self.lib,b,3)
        note(self.lib,b,0)
        self.assertEqual(self.snap().same_as_previous[0],1)
        self.assertEqual(sum(self.snap().returned_to_two_back),0)

    def test_abc_is_not_an_exact_return_even_if_delta_counts_equal(self):
        a=[0]*24
        b=[1]*24
        c=[2]*24
        for x in (a,b,c):note(self.lib,x,1)
        self.assertEqual(self.snap().different_from_both[0],1)
        self.assertEqual(sum(self.snap().returned_to_two_back),0)

    def test_gap_of_one_two_three_and_four_vblanks_is_counted_once_each(self):
        for gap in (1,2,3,4):
            with self.subTest(gap=gap):
                self.lib.vh115_reset()
                self.lib.vh115_enable(1)
                a=[0]*24
                b=[0]*24
                b[0]=5
                note(self.lib,a,0)
                note(self.lib,b,1)
                for _ in range(gap):self.lib.vh115_vblank()
                note(self.lib,a,1)
                r=self.snap()
                self.assertEqual(r.consecutive_triplets,1)
                self.assertEqual(list(r.returned_to_two_back),
                                 [int(i==gap) for i in range(5)])
                old=GapMetrics()
                self.assertEqual(self.lib.vh116_get_gap_metrics(ctypes.byref(old)),0)

    def test_unchanged_triplet_is_never_a_return(self):
        a=[99]*24
        for _ in range(3):note(self.lib,a,0)
        self.assertEqual(self.snap().same_as_previous[0],1)
        self.assertEqual(sum(self.snap().returned_to_two_back),0)

    def test_four_handler_sequence_can_have_distinct_nonoverlapping_returns(self):
        a=[0]*24
        b=[1]*24
        for x in (a,b,a,b):note(self.lib,x,1)
        m=self.snap()
        self.assertEqual(m.consecutive_triplets,2)
        self.assertEqual(m.returned_to_two_back[0],2)

    def test_reset_wipes_two_previous_value_arrays_and_triplet_counters(self):
        a=[0xffff]*24
        b=[12]*24
        note(self.lib,a,0)
        note(self.lib,b,1)
        note(self.lib,a,1)
        self.assertEqual(self.snap().returned_to_two_back[0],1)
        self.lib.vh115_reset()
        self.assertEqual(self.lib.vh115_sample_cache_erased(),1)
        out=Triplets()
        self.assertNotEqual(self.lib.vh117_get_triplet_metrics(ctypes.byref(out)),0)
        self.lib.vh115_enable(1)
        note(self.lib,[0]*24,0)
        self.assertEqual(self.snap().consecutive_triplets,0)

    def test_fifth_vblank_and_invalid_sample_fail_closed(self):
        a=[0]*24
        b=[1]*24
        note(self.lib,a,0)
        note(self.lib,b,1)
        for _ in range(5):self.lib.vh115_vblank()
        note(self.lib,a,1)
        m=Triplets()
        self.assertNotEqual(self.lib.vh117_get_triplet_metrics(ctypes.byref(m)),0)
        self.lib.vh115_reset()
        self.lib.vh115_enable(1)
        note(self.lib,a,0)
        note(self.lib,b,1)
        note(self.lib,a,25)
        self.assertNotEqual(self.lib.vh117_get_triplet_metrics(ctypes.byref(m)),0)

    def test_v115_legacy_abi_remains_identical_and_v116_metrics_still_available(self):
        self.assertEqual(ctypes.sizeof(Metrics),8*4)
        self.assertEqual(ctypes.sizeof(GapMetrics),15*4)
        a=[0]*24
        note(self.lib,a,0)
        note(self.lib,a,0)
        note(self.lib,a,0)
        old=Metrics()
        self.assertEqual(self.lib.vh115_get_metrics(ctypes.byref(old)),0)
        self.assertEqual(old.handlers,3)
        self.assertEqual(old.equal_delta_identical_24_values,2)
        self.assertEqual(self.snap().same_as_previous[0],1)

    def test_emulator_workflow_requires_native_triplet_witness(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("apply_map02_v117_pcsx_rearmed",flow)
        self.assertIn("VH117_TRIPLETS_PASS",flow)
        self.assertIn("v117-triplet-summary.json",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
