#!/usr/bin/env python3
"""v94: native C ABI cache invalidation, tamper refusal and private audit tests."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v93_dual_lanes import fixture as v93_fixture,NativeEvent,encode
from tools.summarize_map02_v93_dual_lanes import summarize as summarize_v93
from tools.summarize_map02_v94_cached_snapshot import summarize
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=v93_fixture()
    for name,value in [
        ("snapshot_cached_reads",128),
        ("snapshot_invalidation_proven",1),
        ("snapshot_verified_reads",128)
    ]:
        rows.append(dict(kind=name,value=value,seq=len(rows)+1,cycle=0,frame=0))
    return rows

class NativeCachedSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        tools=ROOT/"tools"
        out=Path(cls.temp.name)/"libvh94.so"
        for ver,part in ((80,"native_timeline"),(81,"event_jsonl")):
            shutil.copyfile(tools/f"map02_v{ver}_{part}.h",
                            Path(cls.temp.name)/f"vh{ver}_{part}.h")
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-shared","-fPIC",str(tools/"map02_v80_native_timeline.c"),
                        str(tools/"map02_v81_event_jsonl.c"),"-I",cls.temp.name,
                        "-o",str(out)],check=True,capture_output=True)
        cls.dll=ctypes.CDLL(str(out))
        cls.dll.vh80_record.argtypes=[ctypes.c_uint32]*4
        cls.dll.vh80_events.restype=ctypes.POINTER(NativeEvent)
        cls.dll.vh80_count.restype=ctypes.c_uint
        cls.dll.vh94_merge_runs.restype=ctypes.c_uint
        cls.dll.vh94_cache_hits.restype=ctypes.c_uint
        cls.dll.vh94_verify_runs.restype=ctypes.c_uint
        cls.dll.vh94_snapshot_check.restype=ctypes.c_int
        cls.dll.vh81_format_jsonl.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        cls.dll.vh81_format_jsonl.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.dll.vh80_reset()
        self.dll.vh80_record(1,0,100,7)
        self.dll.vh80_record(8,6,0,0)
        self.dll.vh80_record(1,0,200,8)
    def test_128_repeated_reads_only_one_merge(self):
        self.assertEqual(self.dll.vh94_snapshot_check(),-1)
        addr=ctypes.addressof(self.dll.vh80_events().contents)
        self.assertEqual(self.dll.vh94_merge_runs(),1)
        for _ in range(128):
            pointer=self.dll.vh80_events()
            self.assertEqual(ctypes.addressof(pointer.contents),addr)
            self.assertEqual(self.dll.vh94_snapshot_check(),0)
        self.assertEqual(self.dll.vh94_merge_runs(),1)
        self.assertEqual(self.dll.vh94_cache_hits(),128)
        self.assertEqual(self.dll.vh94_verify_runs(),128)
    def test_mutation_invalidates_and_exactly_one_rebuild(self):
        view=self.dll.vh80_events()
        self.assertEqual(view[2].sequence,3)
        self.dll.vh80_record(79,128,0,0)
        self.assertEqual(self.dll.vh94_snapshot_check(),-1)
        self.assertEqual(self.dll.vh94_merge_runs(),1)
        second=self.dll.vh80_events()
        self.assertEqual(second[3].sequence,4)
        self.assertEqual(second[3].kind,79)
        self.assertEqual(self.dll.vh94_merge_runs(),2)
        self.assertEqual(self.dll.vh94_snapshot_check(),0)
        self.dll.vh80_events()
        self.assertEqual(self.dll.vh94_merge_runs(),2)
    def test_native_cached_memory_tamper_fails_closed(self):
        view=self.dll.vh80_events()
        value=view[1].value
        view[1].value=0xdeadbeef
        self.assertEqual(self.dll.vh94_snapshot_check(),-1)
        buf=ctypes.create_string_buffer(524288)
        self.assertEqual(self.dll.vh81_format_jsonl(buf,len(buf)),-1)
        self.assertEqual(self.dll.vh94_merge_runs(),1)
        view[1].value=value
        self.assertEqual(self.dll.vh94_snapshot_check(),0)
        self.assertGreater(self.dll.vh81_format_jsonl(buf,len(buf)),0)
    def test_reset_requires_fresh_merged_snapshot(self):
        self.dll.vh80_events()
        self.dll.vh80_reset()
        self.assertEqual(self.dll.vh94_snapshot_check(),-1)
        self.assertEqual(self.dll.vh94_merge_runs(),0)
        self.dll.vh80_record(1,0,100,7)
        self.dll.vh80_record(1,0,200,8)
        self.dll.vh80_events()
        self.assertEqual(self.dll.vh94_merge_runs(),1)
        self.assertEqual(self.dll.vh94_snapshot_check(),0)

class V94Proof(unittest.TestCase):
    def test_exact_tail_and_existing_checkpoint(self):
        r=summarize(encode(fixture()))
        self.assertEqual(r["unchanged_native_cached_reads"],128)
        self.assertTrue(r["native_stale_view_invalidation_observed"])
        self.assertEqual(r["final_private_journal_events"],
                         r["prior_checkpoint_native_events"]+3)
        self.assertFalse(r["HD_replacement_approved"])
    def test_v93_checkpoint_remains_independently_valid(self):
        r=summarize_v93(encode(fixture()))
        self.assertGreater(r["merged_private_events"],4096)
    def test_refuse_misreported_cached_reads(self):
        rows=fixture();rows[-3]["value"]=127
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_missing_invalidation(self):
        rows=fixture();rows[-2]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_missing_integrity_checks(self):
        rows=fixture();rows[-1]["value"]=127
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_duplicate_tail(self):
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,e in enumerate(rows):e["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_tampered_timestamps(self):
        rows=fixture();rows[-1]["cycle"]=90
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_truncated(self):
        rows=fixture();rows.pop()
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_opt_in_and_pinned_source_requirements(self):
        code=(ROOT/"tools/apply_map02_v94_pcsx_rearmed.py").read_text()
        for token in ("apply_v93(root)","--vh94-cached-journal-smoke",
                      "vh94_snapshot_check()!=0","vh94_merge_runs()!=first_merges",
                      "vh94_cache_hits()-first_hits!=128u",
                      "vh94_verify_runs()-first_verified!=128u",
                      "VH94_SNAPSHOT_PASS","VH94_STALE_SNAPSHOT_REFUSED",
                      "original_retail_MAP02_verified=False",
                      "HD_replacement_approved=False"):
            self.assertIn(token,code)

if __name__=="__main__":unittest.main()
