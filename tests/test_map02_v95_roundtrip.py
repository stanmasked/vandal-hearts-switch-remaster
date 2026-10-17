#!/usr/bin/env python3
"""v95 native C repeated private JSONL serialization and fail-closed audits."""
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
from test_map02_v94_cached_snapshot import fixture as v94_fixture,NativeEvent,encode
from tools.summarize_map02_v94_cached_snapshot import summarize as prior
from tools.summarize_map02_v95_roundtrip import summarize,KINDS,EXPECTED
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=v94_fixture()
    for name,value in zip(KINDS,EXPECTED):
        rows.append(dict(kind=name,seq=len(rows)+1,value=value,cycle=0,frame=0))
    return rows

class NativeIncrementalSerializations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which(os.environ.get("CC","cc"))
        if not cc: raise unittest.SkipTest("native C compiler unavailable")
        cls.temp=tempfile.TemporaryDirectory()
        td=Path(cls.temp.name);src=ROOT/"tools"
        for version,suffix in ((80,"native_timeline"),(81,"event_jsonl")):
            shutil.copyfile(src/f"map02_v{version}_{suffix}.h",
                            td/f"vh{version}_{suffix}.h")
        out=td/"libvh95.so"
        subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror","-fPIC",
                        "-shared",str(src/"map02_v80_native_timeline.c"),
                        str(src/"map02_v81_event_jsonl.c"),"-I",str(td),
                        "-o",str(out)],check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(out))
        cls.lib.vh80_record.argtypes=[ctypes.c_uint32]*4
        cls.lib.vh80_events.restype=ctypes.POINTER(NativeEvent)
        cls.lib.vh80_count.restype=ctypes.c_uint
        cls.lib.vh94_snapshot_check.restype=ctypes.c_int
        cls.lib.vh94_merge_runs.restype=ctypes.c_uint
        cls.lib.vh81_format_jsonl.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        cls.lib.vh81_format_jsonl.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.lib.vh80_reset()
        self.lib.vh80_record(1,0,100,7)
        self.lib.vh80_record(8,17,0,0)
        self.lib.vh80_record(1,0,200,8)
    def export(self):
        raw=ctypes.create_string_buffer(524288)
        n=self.lib.vh81_format_jsonl(raw,len(raw))
        self.assertGreater(n,0)
        return raw.raw[:n]
    def test_eight_append_rebuild_exact_prefix_and_replay(self):
        old=self.export()
        started=self.lib.vh94_merge_runs()
        for index in range(8):
            prior_count=self.lib.vh80_count()
            old_merges=self.lib.vh94_merge_runs()
            self.lib.vh80_record(82+index,index+1,0,0)
            self.assertEqual(self.lib.vh94_snapshot_check(),-1)
            events=self.lib.vh80_events()
            self.assertEqual(events[prior_count].sequence,prior_count+1)
            self.assertEqual(events[prior_count].kind,82+index)
            self.assertEqual(self.lib.vh94_merge_runs(),old_merges+1)
            current=self.export()
            self.assertTrue(current.startswith(old))
            self.assertEqual(current,self.export())
            self.assertEqual(self.lib.vh94_merge_runs(),old_merges+1)
            old=current
        self.assertEqual(self.lib.vh94_merge_runs()-started,8)
    def test_source_lane_corruption_after_caching_refused(self):
        self.export()
        events=self.lib.vh80_events()
        old=events[1].value
        events[1].value=old^0x1234
        self.assertEqual(self.lib.vh94_snapshot_check(),-1)
        raw=ctypes.create_string_buffer(524288)
        self.assertEqual(self.lib.vh81_format_jsonl(raw,len(raw)),-1)
        events[1].value=old
        self.assertEqual(self.lib.vh94_snapshot_check(),0)
        self.assertGreater(self.lib.vh81_format_jsonl(raw,len(raw)),0)

class NativeV95Audit(unittest.TestCase):
    def test_full_roundtrip_and_parent_checkpoint(self):
        r=summarize(encode(fixture()))
        self.assertEqual(r["incremental_append_rounds"],8)
        self.assertEqual(r["private_in_memory_JSONL_serializations"],16)
        self.assertEqual(r["native_stale_view_refusals"],8)
        self.assertEqual(r["final_private_journal_events"],
                         r["v94_checkpoint_private_events"]+13)
        self.assertFalse(r["retail_MAP02_verified"])
        self.assertFalse(r["HD_replacement_approved"])
        self.assertEqual(prior(encode(fixture()))["unchanged_native_cached_reads"],128)
    def test_refuse_skipped_round(self):
        rows=fixture();rows[-11]["value"]=99
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_swapped_round_kinds(self):
        rows=fixture();rows[-12]["kind"],rows[-13]["kind"]=rows[-13]["kind"],rows[-12]["kind"]
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_skipped_byte_prefix(self):
        rows=fixture();rows[-5]["value"]=7
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_short_second_memory_export(self):
        rows=fixture();rows[-4]["value"]=15
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_repeated_merge(self):
        rows=fixture();rows[-3]["value"]=9
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_missing_stale_guard(self):
        rows=fixture();rows[-2]["value"]=7
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_duplicate_suffix(self):
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,r in enumerate(rows):r["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_fake_GPU_cycle_or_frame(self):
        rows=fixture();rows[-1]["cycle"]=4
        with self.assertRaises(Refused):summarize(encode(rows))
        rows=fixture();rows[-2]["frame"]=9
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_no_original_retail_claim_or_HD(self):
        s=(ROOT/"tools/apply_map02_v95_pcsx_rearmed.py").read_text()
        for v in ("apply_v94(root)","--vh95-snapshot-roundtrip-smoke",
                  "memcmp(next_json,previous_json",
                  "memcmp(previous_json,next_json",
                  "vh94_snapshot_check()==0",
                  "VH95_ROUNDTRIP_PASS",
                  "native_worker_drained_before_snapshots=True",
                  "original_retail_MAP02_verified=False",
                  "HD_replacement_approved=False"):
            self.assertIn(v,s)
if __name__=="__main__":unittest.main()
