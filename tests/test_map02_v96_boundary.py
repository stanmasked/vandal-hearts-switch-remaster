#!/usr/bin/env python3
"""v96: native C full-capacity two-lane snapshots and fail-closed overflow.

Tests actual original exported C functions at exactly 4096 detailed and 256
aggregate events. Overflow must not mutate any earlier byte or sequence,
but it MUST permanently refuse private export until diagnostic reset.
"""
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
from test_map02_v95_roundtrip import fixture as v95_fixture,NativeEvent,encode
from tools.summarize_map02_v96_boundary import summarize,KINDS,DETAIL_TYPES
from tools.summarize_map02_v95_roundtrip import summarize as prior
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=v95_fixture()
    detailed=sum(row["kind"] in DETAIL_TYPES for row in rows)
    for kind,value in (
        (KINDS[0],4096-detailed),
        (KINDS[1],256-(len(rows)-detailed)-3),
        (KINDS[2],2),
    ):
        rows.append(dict(kind=kind,value=value,seq=len(rows)+1,
                         cycle=0,frame=0))
    return rows

class NativeCapacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        td=Path(cls.temp.name);tools=ROOT/"tools"
        for v,suffix in ((80,"native_timeline"),(81,"event_jsonl")):
            shutil.copyfile(tools/f"map02_v{v}_{suffix}.h",
                            td/f"vh{v}_{suffix}.h")
        binary=td/"libvh96.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-fPIC","-shared",
                        str(tools/"map02_v80_native_timeline.c"),
                        str(tools/"map02_v81_event_jsonl.c"),
                        "-I",str(td),"-o",str(binary)],
                       check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(binary))
        cls.lib.vh80_record.argtypes=[ctypes.c_uint32]*4
        cls.lib.vh80_events.restype=ctypes.POINTER(NativeEvent)
        cls.lib.vh80_count.restype=ctypes.c_uint
        cls.lib.vh80_detailed_count.restype=ctypes.c_uint
        cls.lib.vh80_aggregate_count.restype=ctypes.c_uint
        cls.lib.vh80_dropped.restype=ctypes.c_uint
        cls.lib.vh94_merge_runs.restype=ctypes.c_uint
        cls.lib.vh94_cache_hits.restype=ctypes.c_uint
        cls.lib.vh94_snapshot_check.restype=ctypes.c_int
        cls.lib.vh81_format_jsonl.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        cls.lib.vh81_format_jsonl.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.lib.vh80_reset()
        self.add(1,0,100,7)
        self.add(1,0,200,8)
    def add(self,k,v=0,cycle=0,frame=0):
        self.lib.vh80_record(k,v,cycle,frame)
    def export(self):
        buf=ctypes.create_string_buffer(524288)
        n=self.lib.vh81_format_jsonl(buf,len(buf))
        self.assertGreater(n,0)
        return buf.raw[:n]
    def must_refuse_export(self):
        buf=ctypes.create_string_buffer(524288)
        self.assertEqual(self.lib.vh81_format_jsonl(buf,len(buf)),-1)
    def snapshot_bytes(self):
        ptr=self.lib.vh80_events()
        return ctypes.string_at(ptr,ctypes.sizeof(NativeEvent)*self.lib.vh80_count())
    def prove_refusal_does_not_corrupt_confirmed_snapshot(self,k):
        original=self.export()
        previous=self.snapshot_bytes()
        count=self.lib.vh80_count()
        merges=self.lib.vh94_merge_runs()
        self.add(k,999)
        self.assertEqual(self.lib.vh80_count(),count)
        self.assertEqual(self.lib.vh80_dropped(),1)
        self.assertEqual(self.snapshot_bytes(),previous)
        self.assertEqual(self.lib.vh94_merge_runs(),merges)
        self.assertEqual(self.lib.vh94_snapshot_check(),-1)
        self.must_refuse_export()
        self.assertEqual(len(original.splitlines()),count)
        self.assertTrue(original.startswith(b'{"kind":"vblank"'))
    def test_detail_4096_full_aggregate_still_available(self):
        for i in range(4094):self.add(4,i)
        self.add(8,5)
        self.assertEqual(self.lib.vh80_detailed_count(),4096)
        self.assertEqual(self.lib.vh80_aggregate_count(),1)
        self.prove_refusal_does_not_corrupt_confirmed_snapshot(4)
    def test_aggregate_256_full_detail_still_available(self):
        for i in range(256):self.add(8,i)
        self.assertEqual(self.lib.vh80_detailed_count(),2)
        self.assertEqual(self.lib.vh80_aggregate_count(),256)
        self.prove_refusal_does_not_corrupt_confirmed_snapshot(8)
    def test_alternating_near_both_boundaries_and_byte_prefix(self):
        for i in range(4086):self.add(4,i)
        for i in range(248):self.add(8,i)
        self.assertEqual(self.lib.vh80_detailed_count(),4088)
        self.assertEqual(self.lib.vh80_aggregate_count(),248)
        previous=self.export()
        merges=self.lib.vh94_merge_runs()
        for i in range(8):
            self.add(4,4100+i)
            self.add(8,250+i)
            updated=self.export()
            self.assertTrue(updated.startswith(previous))
            self.assertEqual(updated,self.export())
            self.assertEqual(self.lib.vh94_merge_runs(),merges+i+1)
            self.assertEqual(self.lib.vh94_snapshot_check(),0)
            previous=updated
        self.assertEqual(self.lib.vh80_detailed_count(),4096)
        self.assertEqual(self.lib.vh80_aggregate_count(),256)
        self.assertEqual(self.lib.vh80_count(),4352)
        self.assertEqual(len(previous.splitlines()),4352)
        sealed=self.snapshot_bytes()
        first_merges=self.lib.vh94_merge_runs()
        self.add(4,22)
        self.add(8,22)
        self.assertEqual(self.lib.vh80_dropped(),2)
        self.assertEqual(self.lib.vh80_count(),4352)
        self.assertEqual(self.snapshot_bytes(),sealed)
        self.assertEqual(self.lib.vh94_merge_runs(),first_merges)
        self.must_refuse_export()
    def test_invalid_kind_is_fail_closed_without_rebuilding_prior_snapshot(self):
        original=self.export()
        previous=self.snapshot_bytes()
        merges=self.lib.vh94_merge_runs()
        self.add(999,0)
        self.assertEqual(self.lib.vh80_dropped(),1)
        self.assertEqual(self.lib.vh94_merge_runs(),merges)
        self.assertEqual(self.snapshot_bytes(),previous)
        self.assertEqual(self.lib.vh94_snapshot_check(),-1)
        self.must_refuse_export()
        self.assertEqual(len(original.splitlines()),2)

class V96PrivateProof(unittest.TestCase):
    def test_valid_checkpoint_recounts_real_event_kinds(self):
        p=summarize(encode(fixture()))
        self.assertGreater(p["private_events"],4096)
        self.assertGreater(p["native_detailed_lane_remaining"],0)
        self.assertGreater(p["native_aggregate_lane_remaining"],0)
        self.assertEqual(p["native_successful_replayed_serializations"],2)
        self.assertFalse(p["real_retail_MAP02_verified"])
        self.assertFalse(p["HD_replacement_approved"])
    def test_v95_predecessor_independently_valid(self):
        self.assertEqual(prior(encode(fixture()))["incremental_append_rounds"],8)
    def test_refuse_forged_detail_free_slots(self):
        rows=fixture();rows[-3]["value"]+=1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_forged_aggregate_free_slots(self):
        rows=fixture();rows[-2]["value"]-=1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_wrong_replay_count(self):
        rows=fixture();rows[-1]["value"]=1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_missing_last_metric(self):
        rows=fixture();rows.pop()
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_repeated_capacity_event(self):
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,e in enumerate(rows):e["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_forged_host_timestamps(self):
        rows=fixture();rows[-1]["cycle"]=999
        with self.assertRaises(Refused):summarize(encode(rows))
        rows=fixture();rows[-2]["frame"]=33
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_opt_in_provenance_and_single_file_publication(self):
        src=(ROOT/"tools/apply_map02_v96_pcsx_rearmed.py").read_text()
        for part in (
            "apply_v95(root)","--vh96-boundary-smoke",
            "aggregates+3u",
            "memcmp(after_json,before_json",
            "vh94_snapshot_check()==0",
            "VH96_BOUNDARY_PASS",
            "runtime_v96_verified=False",
            "retail_MAP02_verified=False",
            "HD_replacement_approved=False",
        ):
            self.assertIn(part,src)

if __name__=="__main__":unittest.main()
