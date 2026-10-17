#!/usr/bin/env python3
"""v85 synthetic counter contract + C-backed source store tracking regressions."""
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
sys.path.insert(0,str(ROOT))
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v85_native_stores import summarize

def sample():
    contents=[
      ("gp1_mmio",0xe1000020,80,0),
      ("vblank",0,100,10),
      ("gp0_unai_handled",0x600000ff,0,0),
      ("unai_sample_delta",1,0,0),
      ("unai_store_count",4,0,0),
      ("unai_same_store_count",1,0,0),
      ("gp0_unai_handled",0xe1000020,0,0),
      ("unai_sample_delta",0,0,0),
      ("unai_store_count",0,0,0),
      ("unai_same_store_count",0,0,0),
      ("gp1_mmio",0x01000000,150,0),
      ("vblank",0,200,11),
      ("vblank",0,300,12),
      ("vblank",0,400,13),
    ]
    return [dict(kind=k,seq=i+1,value=v,cycle=c,frame=f)
            for i,(k,v,c,f) in enumerate(contents)]

def encode(rows):
    return "".join(json.dumps(x,separators=(",",":"))+"\n" for x in rows).encode()

class V85Native(unittest.TestCase):
    def test_disambiguates_genuine_store_and_same_value_store(self):
        report=summarize(encode(sample()))
        self.assertEqual(report["native_store_attempts"],4)
        self.assertEqual(report["native_stores_writing_previous_value"],1)
        self.assertEqual(report["native_stores_writing_new_value"],3)
        self.assertEqual(report["handlers_with_zero_observed_stores"],1)
        self.assertFalse(report["complete_unai_dma_asm_or_legacy_pixel_write_coverage"])
        self.assertFalse(report["HD_replacement_approved"])
    def test_refuses_more_same_than_total(self):
        events=sample()
        events[5]["value"]=5
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuses_missing_pair(self):
        events=sample()
        del events[5]
        for item in events[5:]:item["seq"]-=1
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuses_forged_native_timestamp(self):
        events=sample()
        events[4]["cycle"]=123
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuses_counter_overflow_sentinel(self):
        events=sample()
        events[4]["value"]=0xffffffff
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuses_fixture_without_same_writes(self):
        events=sample()
        events[5]["value"]=0
        with self.assertRaises(Refused):summarize(encode(events))
    def test_source_scope_and_semantic_claims(self):
        src=(ROOT/"tools/apply_map02_v85_pcsx_rearmed.py").read_text()
        self.assertIn("if n!=22",src)
        self.assertIn('pixel[{index}] = rgb;',src)
        self.assertIn("vh85_note_store",src)
        self.assertIn("vh85_write_overflow()?UINT32_MAX",src)
        self.assertIn("vh85_native_store_smoke = 1",src)
        self.assertIn("full_unai_dma_and_legacy_write_provenance_verified=False",src)
        self.assertIn("HD_replacement_approved=False",src)
    def test_actual_c_counter_abi(self):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:self.skipTest("compiler missing")
        with tempfile.TemporaryDirectory() as td:
            shutil.copyfile(ROOT/"tools/map02_v80_native_timeline.h",Path(td)/"vh80_native_timeline.h")
            so=Path(td)/"probe.so"
            subprocess.run([cc,"-shared","-fPIC","-std=c11","-Wall","-Wextra","-Werror",
                "-I",td,str(ROOT/"tools/map02_v80_native_timeline.c"),"-o",str(so)],
                check=True,capture_output=True)
            lib=ctypes.CDLL(str(so))
            lib.vh85_note_store.argtypes=[ctypes.c_uint32,ctypes.c_uint32]
            lib.vh84_set_sampling.argtypes=[ctypes.c_int]
            lib.vh80_reset()
            lib.vh85_note_store(7,7)
            self.assertEqual(lib.vh85_store_count(),0) # disabled
            lib.vh84_set_sampling(1)
            lib.vh85_reset_command()
            lib.vh85_note_store(7,7)
            lib.vh85_note_store(7,9)
            lib.vh85_note_store(9,9)
            self.assertEqual(lib.vh85_store_count(),3)
            self.assertEqual(lib.vh85_same_store_count(),2)
            self.assertEqual(lib.vh85_write_overflow(),0)
            lib.vh85_reset_command()
            self.assertEqual(lib.vh85_store_count(),0)
            self.assertEqual(lib.vh85_same_store_count(),0)

if __name__=="__main__":unittest.main()
