#!/usr/bin/env python3
"""GCC/Clang native equality for 0..4 observed VBlank boundaries."""
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


class GapMetrics(ctypes.Structure):
    _fields_=[
        ("equal_count_identical",ctypes.c_uint32*5),
        ("equal_count_different",ctypes.c_uint32*5),
        ("different_count",ctypes.c_uint32*5),
    ]


class V116NativeVBlankGaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("C compiler unavailable")
        cls.tmp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        folder=Path(cls.tmp.name)
        shutil.copyfile(ROOT/"tools/map02_v115_sample_identity.h",
                        folder/"vh115_sample_identity.h")
        output=folder/"libvh116.so"
        run=subprocess.run([
            cc,"-std=c11","-Wall","-Wextra","-Werror",
            "-shared","-fPIC","-I",str(folder),
            str(ROOT/"tools/map02_v115_sample_identity.c"),
            "-o",str(output)
        ],capture_output=True,text=True)
        if run.returncode:raise AssertionError(run.stderr)
        cls.lib=native(output)
        cls.lib.vh116_get_gap_metrics.argtypes=[ctypes.POINTER(GapMetrics)]
        cls.lib.vh116_get_gap_metrics.restype=ctypes.c_int

    def setUp(self):
        self.lib.vh115_reset()
        self.lib.vh115_enable(1)

    def snap(self):
        value=GapMetrics()
        self.assertEqual(self.lib.vh116_get_gap_metrics(ctypes.byref(value)),0)
        return value

    def test_zero_one_and_two_vblank_edges_with_exact_value_discrimination(self):
        lib=self.lib
        src=[0]*24
        note(lib,src,0)
        note(lib,src,0)   # gap0 identical
        lib.vh115_vblank()
        src[3]=123
        note(lib,src,0)   # gap1 different but same delta
        lib.vh115_vblank()
        lib.vh115_vblank()
        note(lib,src,1)   # gap2 changed delta
        self.assertEqual(self.snap().equal_count_identical[0],1)
        self.assertEqual(self.snap().equal_count_different[1],1)
        self.assertEqual(self.snap().different_count[2],1)
        legacy=Metrics()
        self.assertEqual(lib.vh115_get_metrics(ctypes.byref(legacy)),0)
        self.assertEqual(legacy.equal_delta_identical_24_values,1)
        self.assertEqual(legacy.equal_delta_different_24_values,1)
        self.assertEqual(legacy.cross_vblank_different_delta,1)

    def test_exactly_four_vblank_edges_without_intermediate_unai(self):
        lib=self.lib
        src=[8]*24
        note(lib,src,1)
        for _ in range(4):lib.vh115_vblank()
        note(lib,src,1)
        m=self.snap()
        self.assertEqual(m.equal_count_identical[4],1)
        self.assertEqual(sum(m.equal_count_identical),1)
        self.assertEqual(sum(m.equal_count_different),0)
        self.assertEqual(sum(m.different_count),0)
        legacy=Metrics()
        self.assertEqual(lib.vh115_get_metrics(ctypes.byref(legacy)),0)
        self.assertEqual(legacy.cross_vblank_equal_delta_identical,1)

    def test_three_vblank_edges_with_same_delta_and_distinct_pixels(self):
        src=[8]*24
        note(self.lib,src,1)
        for _ in range(3):self.lib.vh115_vblank()
        src[0]=9
        note(self.lib,src,1)
        self.assertEqual(self.snap().equal_count_different[3],1)

    def test_fifth_vblank_is_refused_before_epoch_rollover(self):
        src=[7]*24
        note(self.lib,src,0)
        for _ in range(5):self.lib.vh115_vblank()
        note(self.lib,src,0)
        out=GapMetrics()
        self.assertNotEqual(self.lib.vh116_get_gap_metrics(ctypes.byref(out)),0)
        m=Metrics()
        self.assertNotEqual(self.lib.vh115_get_metrics(ctypes.byref(m)),0)

    def test_secure_reset_clears_bins_and_24_previous_values(self):
        note(self.lib,[0xffff]*24,1)
        self.lib.vh115_vblank()
        note(self.lib,[0]*24,1)
        self.assertEqual(self.snap().equal_count_different[1],1)
        self.lib.vh115_reset()
        self.assertEqual(self.lib.vh115_sample_cache_erased(),1)
        m=GapMetrics()
        self.assertNotEqual(self.lib.vh116_get_gap_metrics(ctypes.byref(m)),0)
        self.lib.vh115_enable(1)
        note(self.lib,[0]*24,1)
        self.assertEqual(sum(self.snap().equal_count_different),0)

    def test_disallowed_missing_samples_fail_closed(self):
        short=(ctypes.c_uint16*23)(*([1]*23))
        self.lib.vh115_note(short,23,2)
        note(self.lib,[1]*24,2)
        m=GapMetrics()
        self.assertNotEqual(self.lib.vh116_get_gap_metrics(ctypes.byref(m)),0)

    def test_legacy_v115_metrics_struct_remains_unchanged(self):
        header=(ROOT/"tools/map02_v115_sample_identity.h").read_text()
        first=header.split("} vh115_metrics;")[0]
        self.assertNotIn("equal_count_identical[",first)
        self.assertIn("} vh116_gap_metrics;",header)
        self.assertIn("vh116_get_gap_metrics",header)

    def test_real_unai_workflow_integrates_non_pixel_gap_report(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("apply_map02_v116_pcsx_rearmed",workflow)
        self.assertIn("VH116_GAPS_PASS",workflow)
        self.assertIn("v116-sample-gap-summary.json",workflow)
        self.assertIn("path: proof/public/",workflow)


if __name__=="__main__":
    unittest.main()
