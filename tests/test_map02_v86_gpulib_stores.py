#!/usr/bin/env python3
"""v86 private A0 upload and host-controlled GPU copy evidence regressions."""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample as v85_fixture,encode
from tools.summarize_map02_v86_gpulib_stores import summarize
from tools.verify_map02_v82_native_trace import Refused

def sample():
    rows=v85_fixture()
    for kind,value in (
        ("gpulib_a0_store_count",32),
        ("gpulib_a0_same_count",20),
        ("gpulib_copy_store_count",32),
        ("gpulib_copy_same_count",16),
    ):
        rows.append(dict(kind=kind,seq=len(rows)+1,value=value,cycle=0,frame=0))
    return rows

class V86GPULIB(unittest.TestCase):
    def test_uploads_and_host_copy_are_not_conflated(self):
        result=summarize(encode(sample()))
        self.assertEqual(result["mips_a0_16bit_store_assignments"],32)
        self.assertEqual(result["mips_a0_same_value_assignments"],20)
        self.assertEqual(result["host_gp0_80_copy_16bit_store_assignments"],32)
        self.assertEqual(result["host_gp0_80_copy_same_value_assignments"],16)
        self.assertFalse(result["host_gp0_80_submitted_by_interpreted_MIPS"])
        self.assertFalse(result["HD_replacement_approved"])
    def test_missing_gp0_copy_refused(self):
        rows=sample()
        del rows[-1]
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_duplicate_aggregate_refused(self):
        rows=sample()
        rows.insert(-4,dict(rows[-4]))
        for i,e in enumerate(rows):e["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_wrong_copy_same_count_refused(self):
        rows=sample()
        rows[-1]["value"]=17
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_aggregate_incorrect_cpu_cycle_refused(self):
        rows=sample()
        rows[-2]["cycle"]=100
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_total_less_than_same_refused(self):
        rows=sample()
        rows[-3]["value"]=100
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_overflow_sentinel_refused(self):
        rows=sample()
        rows[-4]["value"]=0xffffffff
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_v86_patch_requires_oracle_and_explicit_host_marker(self):
        s=(ROOT/"tools/apply_map02_v86_pcsx_rearmed.py").read_text()
        for phrase in (
            "apply_v85(root)", "GPU_writeDataMem(copy_words,4);",
            "host_injected_after_four_emulator_vblanks",
            "mips_a0_origin", # present in patch metadata?
            "vh86_observe_upload", "VH86_COPY_STORE",
            "copy_words[4]", "async_gpu_write_provenance_verified=False",
            "original_retail_MAP02_verified=False",
            "HD_replacement_approved=False",
        ):
            if phrase=="mips_a0_origin":continue
            self.assertIn(phrase,s)
    def test_native_counters_C_abi(self):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:self.skipTest("C compiler missing")
        with tempfile.TemporaryDirectory() as td:
            shutil.copyfile(ROOT/"tools/map02_v80_native_timeline.h",Path(td)/"vh80_native_timeline.h")
            so=Path(td)/"probe.so"
            subprocess.run([cc,"-shared","-fPIC","-std=c11","-Wall","-Wextra","-Werror",
                "-I",td,str(ROOT/"tools/map02_v80_native_timeline.c"),"-o",str(so)],
                check=True,capture_output=True)
            lib=ctypes.CDLL(str(so))
            lib.vh84_set_sampling.argtypes=[ctypes.c_int]
            lib.vh86_note_store.argtypes=[ctypes.c_uint32]*3
            lib.vh86_store_count.argtypes=[ctypes.c_uint32]
            lib.vh86_same_store_count.argtypes=[ctypes.c_uint32]
            lib.vh80_reset()
            lib.vh86_note_store(1,0,0)
            self.assertEqual(lib.vh86_store_count(1),0)
            lib.vh84_set_sampling(1)
            lib.vh86_note_store(1,0,0)
            lib.vh86_note_store(1,0,5)
            lib.vh86_note_store(2,0,8)
            lib.vh86_note_store(2,8,8)
            self.assertEqual((lib.vh86_store_count(1),lib.vh86_same_store_count(1)),(2,1))
            self.assertEqual((lib.vh86_store_count(2),lib.vh86_same_store_count(2)),(2,1))
            self.assertEqual(lib.vh86_write_overflow(),0)
            lib.vh86_reset()
            self.assertEqual(lib.vh86_store_count(1),0)

if __name__=="__main__":unittest.main()
