#!/usr/bin/env python3
"""v91 fail-closed 2-cycle GPU async/sync provenance and retained VRAM tests."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v90_mixed_order import fixture as v90_fixture,encode
from tools.summarize_map02_v90_mixed_order import summarize as v90_summary
from tools.summarize_map02_v91_mode_cycles import summarize,KINDS
from tools.verify_map02_v82_native_trace import Refused

DATA=[(1,1,8,2,2,16,0,1,8,16,8),(0,0,0,2,2,16,0,1,8,16,8)]

def fixture():
    rows=v90_fixture()
    for name,value in zip(KINDS,DATA[0]+DATA[1]):
        rows.append(dict(kind=name,seq=len(rows)+1,value=value,cycle=0,frame=0))
    return rows

class V91Modes(unittest.TestCase):
    def test_both_mode_cycles(self):
        x=summarize(encode(fixture()))
        self.assertEqual(len(x["mode_cycles"]),2)
        self.assertEqual(x["mode_cycles"][0]["worker_A0_accepted"],1)
        self.assertEqual(x["mode_cycles"][1]["worker_A0_accepted"],0)
        for cycle in x["mode_cycles"]:
            self.assertEqual(cycle["worker_GP0_80_completed"],2)
            self.assertEqual(cycle["worker_masked_GP0_80_copies"],1)
            self.assertEqual(cycle["after_worker_shutdown_sync_copy_same"],8)
        self.assertTrue(x["worker_A0_synchronous_fallback_explicitly_permitted"])
        self.assertFalse(x["original_retail_MAP02_verified"])
        self.assertFalse(x["HD_replacement_approved"])
    def test_prior_order_audit_remains_valid(self):
        x=v90_summary(encode(fixture()))
        self.assertEqual(x["worker_order_rolling_hash"],27249034)
    def test_refuse_lost_first_worker_copy(self):
        x=fixture();x[-22+4]["value"]=1
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_lost_second_worker_copy(self):
        x=fixture();x[-11+4]["value"]=1
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_phantom_a0_completion(self):
        x=fixture();x[-22+1]["value"]=2
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_same_color_unexpected_async_copy(self):
        x=fixture();x[-11+6]["value"]=1
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_missing_second_cycle_mask(self):
        x=fixture();x[-11+7]["value"]=0
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_missing_sync_handoff(self):
        x=fixture();x[-11+9]["value"]=0
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_injected_cycle_duplicate(self):
        x=fixture();x.insert(-1,dict(x[-1]))
        for n,item in enumerate(x):item["seq"]=n+1
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_forged_emulator_frame(self):
        x=fixture();x[-22]["frame"]=123
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_forged_emulator_clock(self):
        x=fixture();x[-1]["cycle"]=123
        with self.assertRaises(Refused):summarize(encode(x))
    def test_refuse_missing_tail(self):
        x=fixture();x.pop()
        with self.assertRaises(Refused):summarize(encode(x))
    def test_source_provenance_and_draining(self):
        source=(ROOT/"tools/apply_map02_v91_pcsx_rearmed.py").read_text()
        for token in ("apply_v90(root)","--vh91-repeat-mode-smoke",
            "pl_rearmed_cbs.thread_rendering=1",
            "pl_rearmed_cbs.thread_rendering=0",
            "vh88_async_counter(2)","vh89_copy_metric(2)",
            "GPU_freeze(1,&state,&vram)",
            "VH91_CROSS_ROUND_REFUSED",
            "VH91_CYCLES_PASS rounds=2",
            "vh80_record(first_kind+phase*11+i",
            "host_test_A0_sync_fallback_explicit=True",
            "original_retail_MAP02_verified=False",
            "HD_replacement_approved=False"):
            self.assertIn(token,source)

if __name__=="__main__":unittest.main()
