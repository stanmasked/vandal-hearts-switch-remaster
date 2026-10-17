#!/usr/bin/env python3
"""Source and native C recorder regressions for v80 (synthetic events only)."""
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
from tools import apply_map02_v80_pcsx_rearmed as patch

class Event(ctypes.Structure):
    _fields_=[("sequence",ctypes.c_uint32),("kind",ctypes.c_uint32),
              ("value",ctypes.c_uint32),("cycle",ctypes.c_uint32),("frame",ctypes.c_uint32)]

class V80Source(unittest.TestCase):
    def test_observer_is_bounded(self):
        s=(ROOT/"tools/map02_v80_native_timeline.c").read_text()
        self.assertIn("#define VH80_CAPACITY 4096u",s)
        self.assertIn("if(count>=VH80_CAPACITY",s)
        self.assertIn("dropped++",s)
    def test_instrumentation_observes_only_real_call_sites(self):
        s=(ROOT/"tools/apply_map02_v80_pcsx_rearmed.py").read_text()
        self.assertIn("vh78_vblank_observed_count++;",s)
        self.assertIn("VH80_GP1_MMIO",s)
        self.assertIn("VH80_GPU_DMA2",s)
        self.assertIn("VH80_VBLANK",s)
        self.assertIn("original_retail_MAP02_verified=False",s)
        self.assertIn("HD_replacement_approved=False",s)
    def test_native_recorder(self):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc: self.skipTest("C compiler unavailable")
        with tempfile.TemporaryDirectory() as td:
            so=Path(td)/"libprobe.so"
            shutil.copyfile(ROOT/"tools/map02_v80_native_timeline.h",Path(td)/"vh80_native_timeline.h")
            subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror","-shared","-fPIC",
                            str(ROOT/"tools/map02_v80_native_timeline.c"),"-I",td,"-o",str(so)],
                           check=True,capture_output=True)
            lib=ctypes.CDLL(str(so))
            lib.vh80_reset()
            lib.vh80_record.argtypes=[ctypes.c_uint32]*4
            lib.vh80_events.restype=ctypes.POINTER(Event)
            lib.vh80_count.restype=ctypes.c_uint
            lib.vh80_dropped.restype=ctypes.c_uint
            lib.vh80_record(1,0,100,7)
            lib.vh80_record(2,0x01000000,110,7)
            lib.vh80_record(3,0x1234,120,7)
            self.assertEqual(lib.vh80_count(),3)
            self.assertEqual([(lib.vh80_events()[i].sequence,lib.vh80_events()[i].kind)
                              for i in range(3)],[(1,1),(2,2),(3,3)])
            lib.vh80_record(99,0,0,0)
            self.assertEqual(lib.vh80_dropped(),1)
            for i in range(4093):lib.vh80_record(1,0,i,7)
            self.assertEqual(lib.vh80_count(),4096)
            lib.vh80_record(1,0,0,0)
            self.assertEqual(lib.vh80_dropped(),2)
            lib.vh80_reset()
            self.assertEqual(lib.vh80_count(),0)
            self.assertEqual(lib.vh80_dropped(),0)

if __name__=="__main__": unittest.main()
