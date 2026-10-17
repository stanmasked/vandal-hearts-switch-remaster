#!/usr/bin/env python3
"""v115: actual in-process 24-point identity, no raw private sample export."""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class Metrics(ctypes.Structure):
    _fields_=[
        ("handlers",ctypes.c_uint32),
        ("vblank_edges",ctypes.c_uint32),
        ("equal_delta_identical_24_values",ctypes.c_uint32),
        ("equal_delta_different_24_values",ctypes.c_uint32),
        ("different_delta_counts",ctypes.c_uint32),
        ("cross_vblank_equal_delta_identical",ctypes.c_uint32),
        ("cross_vblank_equal_delta_different",ctypes.c_uint32),
        ("cross_vblank_different_delta",ctypes.c_uint32),
    ]


def native(path):
    lib=ctypes.CDLL(str(path))
    lib.vh115_reset.argtypes=[]
    lib.vh115_enable.argtypes=[ctypes.c_int]
    lib.vh115_vblank.argtypes=[]
    lib.vh115_note.argtypes=[ctypes.POINTER(ctypes.c_uint16),
                             ctypes.c_uint32,ctypes.c_uint32]
    lib.vh115_get_metrics.argtypes=[ctypes.POINTER(Metrics)]
    lib.vh115_get_metrics.restype=ctypes.c_int
    lib.vh115_sample_cache_erased.argtypes=[]
    lib.vh115_sample_cache_erased.restype=ctypes.c_int
    return lib


def note(lib,values,delta):
    assert len(values)==24
    data=(ctypes.c_uint16*24)(*values)
    lib.vh115_note(data,24,delta)


class NativeV115Identity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler missing")
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        output=Path(cls.temp.name)/"libvh115.so"
        subprocess.run([
            cc,"-std=c11","-Wall","-Wextra","-Werror",
            "-shared","-fPIC","-I",str(ROOT/"tools"),
            str(ROOT/"tools/map02_v115_sample_identity.c"),
            "-o",str(output)],
            check=True,capture_output=True)
        cls.lib=native(output)

    def setUp(self):
        self.lib.vh115_reset()
        self.assertEqual(self.lib.vh115_sample_cache_erased(),1)

    def report(self):
        data=Metrics()
        self.assertEqual(self.lib.vh115_get_metrics(ctypes.byref(data)),0)
        return data

    def test_identical_changed_count_not_enough_to_prove_same_values(self):
        lib=self.lib
        lib.vh115_enable(1)
        values=[0]*24
        note(lib,values,1)
        note(lib,values,1)
        values[0]=7
        note(lib,values,1)
        m=self.report()
        self.assertEqual(m.handlers,3)
        self.assertEqual(m.equal_delta_identical_24_values,1)
        self.assertEqual(m.equal_delta_different_24_values,1)
        self.assertEqual(m.different_delta_counts,0)
        self.assertEqual(m.vblank_edges,0)

    def test_exact_identity_even_when_reported_change_counts_differ(self):
        lib=self.lib
        lib.vh115_enable(1)
        values=[20]*24
        note(lib,values,0)
        note(lib,values,4)
        m=self.report()
        self.assertEqual(m.different_delta_counts,1)
        self.assertEqual(m.equal_delta_identical_24_values,0)
        self.assertEqual(m.equal_delta_different_24_values,0)

    def test_cross_vblank_equality_and_difference_counted_without_pixels(self):
        lib=self.lib
        lib.vh115_enable(1)
        values=[0]*24
        note(lib,values,1)
        note(lib,values,1)
        values[0]=1
        note(lib,values,1)
        lib.vh115_vblank()
        note(lib,values,2)
        note(lib,values,2)
        lib.vh115_vblank()
        values[0]=2
        note(lib,values,2)
        m=self.report()
        self.assertEqual(m.handlers,6)
        self.assertEqual(m.vblank_edges,2)
        self.assertEqual(m.equal_delta_identical_24_values,2)
        self.assertEqual(m.equal_delta_different_24_values,2)
        self.assertEqual(m.different_delta_counts,1)
        self.assertEqual(m.cross_vblank_different_delta,1)
        self.assertEqual(m.cross_vblank_equal_delta_different,1)
        self.assertEqual(m.cross_vblank_equal_delta_identical,0)

    def test_two_blank_vblanks_still_one_adjacent_native_pair(self):
        lib=self.lib
        lib.vh115_enable(1)
        values=[4]*24
        note(lib,values,0)
        lib.vh115_vblank()
        lib.vh115_vblank()
        note(lib,values,0)
        m=self.report()
        self.assertEqual(m.handlers,2)
        self.assertEqual(m.vblank_edges,2)
        self.assertEqual(m.equal_delta_identical_24_values,1)
        self.assertEqual(m.cross_vblank_equal_delta_identical,1)

    def test_reset_erases_actual_previous_24_values(self):
        lib=self.lib
        lib.vh115_enable(1)
        note(lib,[0xffff]*24,2)
        self.assertEqual(lib.vh115_sample_cache_erased(),0)
        lib.vh115_reset()
        self.assertEqual(lib.vh115_sample_cache_erased(),1)
        m=Metrics()
        self.assertNotEqual(lib.vh115_get_metrics(ctypes.byref(m)),0)
        lib.vh115_enable(1)
        note(lib,[0]*24,2)
        self.assertEqual(self.report().handlers,1)
        self.assertEqual(self.report().equal_delta_different_24_values,0)

    def test_disabled_and_malformed_sample_count_fail_closed(self):
        lib=self.lib
        note(lib,[1]*24,1)
        m=Metrics()
        self.assertNotEqual(lib.vh115_get_metrics(ctypes.byref(m)),0)
        lib.vh115_enable(1)
        short=(ctypes.c_uint16*23)(*[1]*23)
        lib.vh115_note(short,23,1)
        note(lib,[1]*24,1)
        self.assertNotEqual(lib.vh115_get_metrics(ctypes.byref(m)),0)
        lib.vh115_reset()
        lib.vh115_enable(1)
        note(lib,[1]*24,25)
        self.assertNotEqual(lib.vh115_get_metrics(ctypes.byref(m)),0)

    def test_second_enable_after_observations_refused(self):
        lib=self.lib
        lib.vh115_enable(1)
        note(lib,[3]*24,1)
        lib.vh115_enable(1)
        m=Metrics()
        self.assertNotEqual(lib.vh115_get_metrics(ctypes.byref(m)),0)

    def test_no_new_events_or_opaque_hash_in_canonical_v82_jsonl(self):
        source=(ROOT/"tools/apply_map02_v115_pcsx_rearmed.py").read_text()
        self.assertIn("apply_v104(root)",source)
        self.assertIn("vh115_note(vh115_post,24u,changed)",source)
        self.assertIn("vh115_wipe[vi]=0",source)
        self.assertIn("vh115_vblank()",source)
        self.assertIn("vh115_reset()",source)
        self.assertIn("vh115_sample_identity.o",source)
        self.assertIn("VH115_SAMPLE_IDENTITY_PASS",source)
        self.assertNotIn("vh80_record(VH115_",source)
        self.assertNotIn("sha256",source.lower())
        self.assertNotIn("fnv",source.lower())

    def test_original_v82_timeline_and_event_schema_remain_unmodified(self):
        source=(ROOT/"tools/map02_v80_native_timeline.c").read_text()
        self.assertNotIn("vh115_",source)
        serialized=(ROOT/"tools/map02_v81_event_jsonl.c").read_text()
        self.assertNotIn("vh115_",serialized)
        strict=(ROOT/"tools/verify_map02_v82_native_trace.py").read_text()
        self.assertNotIn("vh115_",strict)

    def test_pinned_full_emulator_checks_only_aggregate_sidecar_log(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("apply_map02_v115_pcsx_rearmed",flow)
        self.assertIn("VH115_SAMPLE_IDENTITY_PASS",flow)
        self.assertIn("v115-sample-identity-summary.json",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
