#!/usr/bin/env python3
"""v93 ABI and adversarial tests of physical dual-lane native GPU journal."""
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
from test_map02_v92_queue_pressure import fixture as v92_fixture,encode
from tools.summarize_map02_v92_queue_pressure import summarize as prior
from tools.summarize_map02_v93_dual_lanes import summarize,DETAIL_TYPES
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=v92_fixture()
    detail=sum(row["kind"] in DETAIL_TYPES for row in rows)
    assert detail<4050
    target=4050-(4050-detail)%4
    for _ in range((target-detail)//4):
        for kind,value in [
            ("gp0_unai_handled",0x600000ff),
            ("unai_sample_delta",0),
            ("unai_store_count",0),
            ("unai_same_store_count",0)
        ]:
            rows.append(dict(kind=kind,value=value,
                             seq=len(rows)+1,cycle=0,frame=0))
    aggregate=len(rows)-target+3
    total=target+aggregate
    for kind,value in [
        ("lane_detail_events",target),
        ("lane_aggregate_events",aggregate),
        ("lane_total_events",total)]:
        rows.append(dict(kind=kind,value=value,seq=len(rows)+1,
                         cycle=0,frame=0))
    assert len(rows)==total>4096
    return rows

class NativeEvent(ctypes.Structure):
    _fields_=[("sequence",ctypes.c_uint32),("kind",ctypes.c_uint32),
              ("value",ctypes.c_uint32),("cycle",ctypes.c_uint32),
              ("frame",ctypes.c_uint32)]

class NativeLanes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc:raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        tools=ROOT/"tools"
        target=Path(cls.temp.name)/"libvh93.so"
        for ver,file in [(80,"native_timeline"),(81,"event_jsonl")]:
            shutil.copyfile(tools/f"map02_v{ver}_{file}.h",
                            Path(cls.temp.name)/f"vh{ver}_{file}.h")
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                        "-shared","-fPIC",str(tools/"map02_v80_native_timeline.c"),
                        str(tools/"map02_v81_event_jsonl.c"),"-I",cls.temp.name,
                        "-o",str(target)],check=True,capture_output=True)
        cls.dll=ctypes.CDLL(str(target))
        cls.dll.vh80_record.argtypes=[ctypes.c_uint32]*4
        cls.dll.vh80_events.restype=ctypes.POINTER(NativeEvent)
        cls.dll.vh80_count.restype=ctypes.c_uint
        cls.dll.vh80_detailed_count.restype=ctypes.c_uint
        cls.dll.vh80_aggregate_count.restype=ctypes.c_uint
        cls.dll.vh80_dropped.restype=ctypes.c_uint
        cls.dll.vh81_format_jsonl.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        cls.dll.vh81_format_jsonl.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):self.dll.vh80_reset()
    def record(self,kind,value=0,cycle=0,frame=0):
        self.dll.vh80_record(kind,value,cycle,frame)
    def test_full_dual_lane_combined_4352_preserves_global_sequence(self):
        self.record(1,0,100,7)
        self.record(8,1,0,0)
        self.record(1,0,200,8)
        for i in range(2047):self.record(4,0x600000ff)
        for i in range(255):self.record(8,i+2)
        for i in range(2047):self.record(4,0x600000ff)
        self.assertEqual(self.dll.vh80_detailed_count(),4096)
        self.assertEqual(self.dll.vh80_aggregate_count(),256)
        self.assertEqual(self.dll.vh80_count(),4352)
        self.assertEqual(self.dll.vh80_dropped(),0)
        events=self.dll.vh80_events()
        self.assertEqual(events[0].kind,1)
        self.assertEqual(events[1].kind,8)
        self.assertEqual(events[2].kind,1)
        self.assertEqual(events[2050].kind,8)
        self.assertEqual([events[i].sequence for i in range(4352)],
                         list(range(1,4353)))
        buf=ctypes.create_string_buffer(524288)
        n=self.dll.vh81_format_jsonl(buf,len(buf))
        self.assertGreater(n,0)
        records=[json.loads(line) for line in buf.raw[:n].decode().splitlines()]
        self.assertEqual(len(records),4352)
        self.assertEqual([r["seq"] for r in records],list(range(1,4353)))
        self.assertEqual(records[0]["kind"],"vblank")
        self.assertEqual(records[1]["kind"],"gpulib_a0_store_count")
        self.assertEqual(records[2050]["kind"],"gpulib_a0_store_count")
    def test_independent_aggregate_lane_capacity_fails_closed(self):
        self.record(1,0,100,7);self.record(1,0,200,8)
        for _ in range(256):self.record(8,1)
        self.assertEqual(self.dll.vh80_count(),258)
        self.record(8,1)
        self.assertEqual(self.dll.vh80_dropped(),1)
        self.assertEqual(self.dll.vh80_count(),258)
        buf=ctypes.create_string_buffer(524288)
        self.assertEqual(self.dll.vh81_format_jsonl(buf,len(buf)),-1)
    def test_independent_detail_lane_capacity_fails_closed(self):
        self.record(1,0,100,7);self.record(1,0,200,8)
        for _ in range(4094):self.record(4,0x600000ff)
        self.record(8,5)
        self.record(4,0x600000ff)
        self.assertEqual(self.dll.vh80_detailed_count(),4096)
        self.assertEqual(self.dll.vh80_aggregate_count(),1)
        self.assertEqual(self.dll.vh80_dropped(),1)
    def test_snapshot_updates_after_new_event(self):
        self.record(1,0,100,7);self.record(1,0,200,8)
        self.assertEqual(self.dll.vh80_events()[1].kind,1)
        self.record(8,17)
        self.assertEqual(self.dll.vh80_events()[2].kind,8)
        self.dll.vh80_reset()
        self.record(1,0,100,7)
        self.assertEqual(self.dll.vh80_events()[0].sequence,1)

class V93AggregateAudit(unittest.TestCase):
    def test_valid_more_than_4096_global_events(self):
        p=summarize(encode(fixture()))
        self.assertGreater(p["merged_private_events"],4096)
        self.assertGreaterEqual(p["detailed_renderer_lane_events"],4047)
        self.assertLessEqual(p["detailed_renderer_lane_events"],4050)
        self.assertTrue(p["original_event_sequence_preserved"])
        self.assertFalse(p["genuine_retail_MAP02_verified"])
        self.assertFalse(p["HD_replacement_approved"])
    def test_predecessor_v92_still_valid(self):
        r=prior(encode(fixture()))
        self.assertTrue(r["all_host_16bit_assignments_verified"])
    def test_refuse_missing_native_event_in_detail_lane(self):
        events=fixture()
        events.pop(-4)
        for i,x in enumerate(events):x["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_wrong_reported_lane_total(self):
        events=fixture();events[-1]["value"]-=1
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_wrong_detail_aggregate_classification(self):
        events=fixture();events[-2]["value"]+=1
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_truncated_suffix(self):
        events=fixture();events.pop()
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_duplicate_suffix_event(self):
        events=fixture();events.insert(-1,dict(events[-1]))
        for i,x in enumerate(events):x["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(events))
    def test_refuse_false_emulator_timestamps(self):
        events=fixture();events[-3]["cycle"]=123
        with self.assertRaises(Refused):summarize(encode(events))
    def test_patch_only_after_original_four_vblank_oracle(self):
        code=(ROOT/"tools/apply_map02_v93_pcsx_rearmed.py").read_text()
        for anchor in ["apply_v92(root)","--vh93-dual-lane-smoke",
                       "VH93_DUAL_LANE_PASS","vh80_detailed_count()",
                       "vh80_aggregate_count()","total<=VH80_CAPACITY_DETAIL",
                       "GPU_writeDataMem(warm,12*3)",
                       "VH93_MERGE_SEQUENCE_REFUSED",
                       "original_retail_MAP02_verified=False",
                       "HD_replacement_approved=False"]:
            self.assertIn(anchor,code)

if __name__=="__main__":unittest.main()
