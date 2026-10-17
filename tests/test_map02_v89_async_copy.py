#!/usr/bin/env python3
"""v89 synthetic private-stream controls for async GP0(80) provenance."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v88_async_dma import fixture as v88_events,encode
from tools.summarize_map02_v88_async_dma import summarize as v88_summary
from tools.summarize_map02_v89_async_copy import summarize
from tools.verify_map02_v82_native_trace import Refused

KINDS=("async_copy_queued","async_copy_completed","async_copy_store_count",
       "async_copy_same_count","async_copy_masked_completed",
       "post_async_sync_copy_stores","post_async_sync_copy_same")
VALUES=(4,4,16,8,2,8,4)

def fixture():
    rows=v88_events()
    for kind,val in zip(KINDS,VALUES):
        rows.append(dict(kind=kind,seq=len(rows)+1,value=val,cycle=0,frame=0))
    return rows

class V89GPUCopy(unittest.TestCase):
    def test_real_worker_vs_sync_transition(self):
        report=summarize(encode(fixture()))
        self.assertEqual(report["async_gp0_80_completed_by_gpu_worker"],4)
        self.assertEqual(report["async_gp0_80_16bit_stores"],16)
        self.assertEqual(report["async_gp0_80_same_value_stores"],8)
        self.assertEqual(report["async_gp0_80_masked_completed"],2)
        self.assertEqual(report["after_worker_sync_gp0_80_16bit_stores"],8)
        self.assertTrue(report["all_v89_GP0_commands_host_submitted"])
        self.assertFalse(report["retail_MAP02_verified"])
        self.assertFalse(report["HD_replacement_approved"])
    def test_v88_parent_still_valid_with_append(self):
        self.assertEqual(v88_summary(encode(fixture()))["async_queued_submissions"],12)
    def test_reject_unexecuted_worker_queue(self):
        rows=fixture();rows[-6]["value"]=3
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_missing_actual_stores(self):
        rows=fixture();rows[-5]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_mask_drop(self):
        rows=fixture();rows[-3]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_sync_fallback_missing(self):
        rows=fixture();rows[-2]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_duplicate_event(self):
        rows=fixture()
        rows.insert(-1,dict(rows[-1]))
        for i,e in enumerate(rows):e["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_forged_worker_cycle(self):
        rows=fixture();rows[-4]["cycle"]=700
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_forged_frame(self):
        rows=fixture();rows[-7]["frame"]=40
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_provenance_worker_and_mode_transition_are_explicit(self):
        src=(ROOT/"tools/apply_map02_v89_pcsx_rearmed.py").read_text()
        for token in (
            "apply_v88(root)","vh89_copy_note_store","vh89_copy_queued",
            "vh89_copy_started","vh89_copy_finished","vh89_copy_active",
            "GPU_writeDataMem(fast_copy,4)","GPU_writeDataMem(masked_copy,4)",
            "GPU_writeData(0xe6000001u)","GPU_writeData(0xe6000000u)",
            "pl_rearmed_cbs.thread_rendering=0","vh86_reset();",
            "VH89_ASYNC_COPY_PASS","original_retail_MAP02_verified=False",
            "HD_replacement_approved=False"
        ):
            self.assertIn(token,src)

if __name__=="__main__":unittest.main()
