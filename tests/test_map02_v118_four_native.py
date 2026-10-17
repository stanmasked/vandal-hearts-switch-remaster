#!/usr/bin/env python3
"""Native exact 24-value A-B-C-A returns with 0–4 VBlank observations."""
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
from test_map02_v117_aba_native import Triplets


class Quads(ctypes.Structure):
    _fields_=[
        ("consecutive_quadruplets",ctypes.c_uint32),
        ("same_as_previous",ctypes.c_uint32*5),
        ("returned_to_two_back",ctypes.c_uint32*5),
        ("returned_to_three_back",ctypes.c_uint32*5),
        ("different_from_all_three",ctypes.c_uint32*5),
    ]


class FourNativeIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("C compiler unavailable")
        cls.tmp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        folder=Path(cls.tmp.name)
        shutil.copyfile(ROOT/"tools/map02_v115_sample_identity.h",
                        folder/"vh115_sample_identity.h")
        lib=folder/"libvh118.so"
        run=subprocess.run(
            [cc,"-std=c11","-Wall","-Wextra","-Werror",
             "-shared","-fPIC","-I",str(folder),
             str(ROOT/"tools/map02_v115_sample_identity.c"),"-o",str(lib)],
            capture_output=True,text=True)
        if run.returncode:raise AssertionError(run.stderr)
        cls.lib=native(lib)
        cls.lib.vh117_get_triplet_metrics.argtypes=[ctypes.POINTER(Triplets)]
        cls.lib.vh117_get_triplet_metrics.restype=ctypes.c_int
        cls.lib.vh118_get_quadruplet_metrics.argtypes=[ctypes.POINTER(Quads)]
        cls.lib.vh118_get_quadruplet_metrics.restype=ctypes.c_int

    def setUp(self):
        self.lib.vh115_reset()
        self.lib.vh115_enable(1)

    def report(self):
        q=Quads()
        self.assertEqual(self.lib.vh118_get_quadruplet_metrics(ctypes.byref(q)),0)
        return q

    def values(self,value):
        return [value]*24

    def test_abca_four_handlers_return_to_first_even_after_two_changes(self):
        for value in (0,1,2,0):note(self.lib,self.values(value),1)
        q=self.report()
        self.assertEqual(q.consecutive_quadruplets,1)
        self.assertEqual(q.returned_to_three_back[0],1)
        self.assertEqual(sum(q.returned_to_two_back),0)

    def test_abcb_returns_to_two_back_not_three(self):
        for value in (0,1,2,1):note(self.lib,self.values(value),1)
        self.assertEqual(self.report().returned_to_two_back[0],1)
        self.assertEqual(sum(self.report().returned_to_three_back),0)

    def test_abcc_repeats_latest_state(self):
        for value in (0,1,2,2):note(self.lib,self.values(value),1)
        q=self.report()
        self.assertEqual(q.same_as_previous[0],1)

    def test_abcd_is_different_from_all(self):
        for value in (0,1,2,3):note(self.lib,self.values(value),1)
        self.assertEqual(self.report().different_from_all_three[0],1)

    def test_priority_with_all_equal_does_not_claim_return(self):
        for _ in range(4):note(self.lib,self.values(7),0)
        q=self.report()
        self.assertEqual(q.same_as_previous[0],1)
        self.assertEqual(sum(q.returned_to_two_back),0)
        self.assertEqual(sum(q.returned_to_three_back),0)

    def test_return_across_zero_one_two_three_four_vblank_edges(self):
        for gap in range(5):
            with self.subTest(gap=gap):
                self.lib.vh115_reset()
                self.lib.vh115_enable(1)
                for x in (0,1,2):note(self.lib,self.values(x),1)
                for _ in range(gap):self.lib.vh115_vblank()
                note(self.lib,self.values(0),1)
                self.assertEqual(list(self.report().returned_to_three_back),
                                 [int(i==gap) for i in range(5)])

    def test_overlapping_four_callback_windows_count_once_each(self):
        for x in (0,1,2,0,1):note(self.lib,self.values(x),1)
        q=self.report()
        self.assertEqual(q.consecutive_quadruplets,2)
        self.assertEqual(q.returned_to_three_back[0],2)

    def test_three_handlers_have_zero_quadruplets(self):
        for x in (0,1,0):note(self.lib,self.values(x),1)
        self.assertEqual(self.report().consecutive_quadruplets,0)

    def test_reset_scrubs_all_three_prior_sample_arrays(self):
        for x in (0xffff,3,7,0xffff):note(self.lib,self.values(x),1)
        self.assertEqual(self.report().returned_to_three_back[0],1)
        self.lib.vh115_reset()
        self.assertEqual(self.lib.vh115_sample_cache_erased(),1)
        q=Quads()
        self.assertNotEqual(self.lib.vh118_get_quadruplet_metrics(ctypes.byref(q)),0)
        self.lib.vh115_enable(1)
        note(self.lib,self.values(0),0)
        self.assertEqual(self.report().consecutive_quadruplets,0)

    def test_five_vblank_events_refused(self):
        for x in (0,1,2):note(self.lib,self.values(x),1)
        for _ in range(5):self.lib.vh115_vblank()
        note(self.lib,self.values(0),1)
        q=Quads()
        self.assertNotEqual(self.lib.vh118_get_quadruplet_metrics(ctypes.byref(q)),0)

    def test_original_v115_metrics_and_v117_triplet_api_intact(self):
        for x in (0,1,2,0):note(self.lib,self.values(x),1)
        old=Metrics()
        third=Triplets()
        self.assertEqual(self.lib.vh115_get_metrics(ctypes.byref(old)),0)
        self.assertEqual(self.lib.vh117_get_triplet_metrics(ctypes.byref(third)),0)
        self.assertEqual(old.handlers,4)
        self.assertEqual(third.consecutive_triplets,2)
        self.assertEqual(self.report().consecutive_quadruplets,1)
        self.assertEqual(ctypes.sizeof(Metrics),32)

    def test_new_pinned_workflow_requires_native_four_handler_witness(self):
        f=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("apply_map02_v118_pcsx_rearmed",f)
        self.assertIn("VH118_QUADRUPLETS_PASS",f)
        self.assertIn("v118-quadruplet-summary.json",f)
        self.assertIn("path: proof/public/",f)


if __name__=="__main__":
    unittest.main()
