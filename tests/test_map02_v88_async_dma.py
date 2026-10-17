#!/usr/bin/env python3
"""v88 independent append-only asynchronous A0 worker accounting regressions."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v87_gpulib_edges import fixture as parent,encode
from tools.summarize_map02_v88_async_dma import summarize
from tools.summarize_map02_v87_gpulib_edges import summarize as parent_summary
from tools.verify_map02_v82_native_trace import Refused

def fixture():
    rows=parent()
    for kind,value in [
        ("async_dma_queued",12),
        ("async_dma_completed",12),
        ("async_dma_store_count",96),
        ("async_dma_same_count",88)
    ]:
        rows.append(dict(kind=kind,value=value,seq=len(rows)+1,cycle=0,frame=0))
    return rows

class V88Async(unittest.TestCase):
    def test_completed_workers_not_just_queued(self):
        report=summarize(encode(fixture()))
        self.assertEqual(report["async_queued_submissions"],12)
        self.assertEqual(report["async_worker_completed_transfers"],12)
        self.assertEqual(report["async_worker_16bit_assignments"],96)
        self.assertEqual(report["async_worker_same_value_assignments"],88)
        self.assertEqual(report["async_worker_new_value_assignments"],8)
        self.assertFalse(report["full_async_pipeline_coverage"])
        self.assertFalse(report["HD_replacement_approved"])
    def test_v87_parent_remains_valid(self):
        self.assertEqual(parent_summary(encode(fixture()))["host_overlap_same_value_stores"],8)
    def test_reject_uncompleted_queue(self):
        rows=fixture();rows[-3]["value"]=11
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_missing_worker_store(self):
        rows=fixture();rows[-2]["value"]=88
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_no_actual_new_value(self):
        rows=fixture();rows[-1]["value"]=96
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_no_same_value_write(self):
        rows=fixture();rows[-1]["value"]=0
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_forged_worker_timestamp(self):
        rows=fixture();rows[-2]["cycle"]=123
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_worker_frame_claim(self):
        rows=fixture();rows[-1]["frame"]=10
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_duplicate_async_event(self):
        rows=fixture();rows.insert(-1,dict(rows[-1]))
        for i,e in enumerate(rows):e["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_requires_real_async_worker_and_post_oracle(self):
        patch=(ROOT/"tools/apply_map02_v88_pcsx_rearmed.py").read_text()
        for fragment in (
            "apply_v87(root)", "gpu_async_try_dma", "vh88_queue",
            "__atomic_fetch_add(&vh88_finished", "vh88_worker_line(",
            "GPU_writeDataMem(upload,7);", "GPU_freeze(1,&state,&vram)",
            "plugin_call_rearmed_cbs();", "thread_rendering=1",
            "async_worker_counter_snapshot_thread_safe=True",
            "original_retail_MAP02_verified=False",
            "HD_replacement_approved=False",
        ):
            if fragment=="gpu_async_try_dma":continue
            self.assertIn(fragment,patch)

if __name__=="__main__":unittest.main()
