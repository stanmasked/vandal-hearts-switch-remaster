#!/usr/bin/env python3
"""v90 tests: fail closed on worker order, mask, and post-async VRAM changes."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v89_async_copy import fixture as v89_events,encode
from tools.summarize_map02_v89_async_copy import summarize as parent
from tools.summarize_map02_v90_mixed_order import summarize,KINDS,EXPECTED
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    events=v89_events()
    for kind,value in zip(KINDS,EXPECTED):
        events.append(dict(kind=kind,value=value,seq=len(events)+1,cycle=0,frame=0))
    return events

class V90Mixed(unittest.TestCase):
    def test_mixed_worker_provenance(self):
        result=summarize(encode(fixture()))
        self.assertEqual(result["async_A0_completed_by_worker"],4)
        self.assertEqual(result["async_GP0_80_completed_by_worker"],3)
        self.assertEqual(result["async_A0_same_value_stores"],8)
        self.assertEqual(result["async_GP0_80_masked_copies"],1)
        self.assertEqual(result["worker_order_rolling_hash"],27249034)
        self.assertTrue(result["mixed_worker_order_proven_for_synthetic_fixture"])
        self.assertFalse(result["HD_replacement_approved"])
        self.assertFalse(result["retail_MAP02_verified"])
    def test_parent_keeps_independent_audit(self):
        self.assertEqual(parent(encode(fixture()))["async_gp0_80_completed_by_gpu_worker"],4)
    def test_reject_missing_queue_completion(self):
        rows=fixture();rows[-13]["value"]=3
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_unexecuted_copy_stores(self):
        rows=fixture();rows[-8]["value"]=16
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_lost_e6_masked_copy(self):
        rows=fixture();rows[-6]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_worker_reordering(self):
        rows=fixture();rows[-4]["value"]=27249035
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_bad_step_count(self):
        rows=fixture();rows[-5]["value"]=6
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_sync_handoff_loss(self):
        rows=fixture();rows[-3]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_changed_same_value_count(self):
        rows=fixture();rows[-1]["value"]=7
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_misplaced_worker_aggregate(self):
        rows=fixture();rows[-6],rows[-7]=rows[-7],rows[-6]
        for i,v in enumerate(rows):v["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_duplicate_aggregate(self):
        rows=fixture()
        rows.insert(-1,dict(rows[-1]))
        for i,v in enumerate(rows):v["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_fabricated_cpu_timestamp(self):
        rows=fixture();rows[-8]["cycle"]=110
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_fabricated_frame(self):
        rows=fixture();rows[-9]["frame"]=14
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_only_real_worker_and_host_phase_fixture(self):
        s=(ROOT/"tools/apply_map02_v90_pcsx_rearmed.py").read_text()
        for token in (
            "apply_v89(root)","vh90_worker_token",
            "vh90_reset();","--vh90-mixed-gpu-order-smoke",
            "GPU_writeDataMem(warm,384*3)","GPU_writeDataMem(copy_red,4)",
            "GPU_writeDataMem(copy_green,4)","GPU_writeDataMem(copy_blue,4)",
            "GPU_writeData(0xe6000001u)",
            "vh88_async_counter(2)","vh89_copy_metric(2)",
            "pl_rearmed_cbs.thread_rendering=0",
            "GPU_writeDataMem(sync_a0,7)",
            "vh80_record(VH90_WORKER_ORDER,order,0,0);",
            "original_retail_MAP02_verified=False",
            "HD_replacement_approved=False",
        ):
            self.assertIn(token,s)

if __name__=="__main__":unittest.main()
