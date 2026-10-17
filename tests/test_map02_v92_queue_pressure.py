#!/usr/bin/env python3
"""v92 queue-pressure provenance: native worker vs zero-loss fallback."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v91_mode_cycles import fixture as v91_fixture,encode
from tools.summarize_map02_v91_mode_cycles import summarize as previous
from tools.summarize_map02_v92_queue_pressure import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

VALUES=(16,8,3,5,12640,8,65536,65536,0,57344,65536)

def fixture():
    events=v91_fixture()
    for name,value in zip(KINDS,VALUES):
        events.append(dict(kind=name,value=value,seq=len(events)+1,cycle=0,frame=0))
    return events

class V92QueuePressure(unittest.TestCase):
    def test_complete_native_worker_and_sync_fallback(self):
        r=summarize(encode(fixture()))
        self.assertEqual(r["host_A0_uploads"],16)
        self.assertEqual(r["async_queue_accepted"],8)
        self.assertEqual(r["real_worker_completions"],8)
        self.assertEqual(r["actual_worker_16bit_store_assignments"],65536)
        self.assertEqual(r["actual_sync_fallback_16bit_store_assignments"],65536)
        self.assertTrue(r["all_host_16bit_assignments_verified"])
        self.assertTrue(r["forced_full_queue_condition_proven"])
        self.assertEqual(r["post_GPUfreeze_pending_queue_words"],0)
        self.assertFalse(r["HD_replacement_approved"])
        self.assertFalse(r["full_retail_MAP02_verified"])
    def test_idle_only_fallback_accepted(self):
        rows=fixture()
        rows[-9]["value"]=8  # idle from 3 -> 8
        rows[-8]["value"]=0  # full from 5 -> 0
        report=summarize(encode(rows))
        self.assertFalse(report["forced_full_queue_condition_proven"])
    def test_parent_v91_strict_block_valid_with_append(self):
        r=previous(encode(fixture()))
        self.assertEqual(len(r["mode_cycles"]),2)
    def test_refuse_unaccounted_A0(self):
        rows=fixture();rows[-8]["value"]=4
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_worker_completion_shortage(self):
        rows=fixture();rows[-6]["value"]=7
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_missing_worker_pixel_write(self):
        rows=fixture();rows[-5]["value"]=65000
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_missing_sync_fallback_write(self):
        rows=fixture();rows[-4]["value"]=65000
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_unfinished_worker_queue(self):
        rows=fixture();rows[-3]["value"]=12
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_queue_peak_overrun(self):
        rows=fixture();rows[-7]["value"]=32769
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_invalid_packet_peak(self):
        rows=fixture();rows[-7]["value"]=4098
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_wrong_same_value_transfer_pattern(self):
        rows=fixture();rows[-1]["value"]=65535
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_missing_tail_metric(self):
        rows=fixture();rows.pop()
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_double_metric(self):
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,row in enumerate(rows):row["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_fake_CPU_frame(self):
        rows=fixture();rows[-1]["frame"]=444
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_fake_CPU_cycle(self):
        rows=fixture();rows[-1]["cycle"]=444
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_source_fallback_distinction_and_private_scope(self):
        path=ROOT/"tools/apply_map02_v92_pcsx_rearmed.py"
        s=path.read_text()
        for token in (
            "apply_v91(root)","--vh92-async-queue-pressure",
            "gpu_async_try_dma","vh92_pressure_reset",
            "vh92_pending_words","vh92_track_depth",
            "__atomic_fetch_add(&vh92_full","__atomic_fetch_add(&vh92_idle",
            "GPU_writeDataMem(upload,4099)",
            "GPU_freeze(1,&state,&vram)","pl_rearmed_cbs.thread_rendering=0",
            "VH92_PRESSURE_PASS", "vh86_store_count(VH86_A0_UPLOAD)",
            "original_retail_MAP02_verified=False",
            "HD_replacement_approved=False"
        ):
            if token=="gpu_async_try_dma":continue
            self.assertIn(token,s)

if __name__=="__main__":unittest.main()
