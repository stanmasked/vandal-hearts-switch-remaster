#!/usr/bin/env python3
"""v84 purely synthetic integrity and readback classification regressions."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v84_unai_samples import summarize

def synthetic_events():
    return [
        dict(kind="gp1_mmio",seq=1,value=0xe1000020,cycle=80,frame=0),
        dict(kind="vblank",seq=2,value=0,cycle=100,frame=20),
        dict(kind="gp0_unai_handled",seq=3,value=0x600000ff,cycle=0,frame=0),
        dict(kind="unai_sample_delta",seq=4,value=3,cycle=0,frame=0),
        dict(kind="gp0_unai_handled",seq=5,value=0xe1000020,cycle=0,frame=0),
        dict(kind="unai_sample_delta",seq=6,value=0,cycle=0,frame=0),
        dict(kind="gp1_mmio",seq=7,value=0x01000000,cycle=150,frame=0),
        dict(kind="vblank",seq=8,value=0,cycle=200,frame=21),
        dict(kind="vblank",seq=9,value=0,cycle=300,frame=22),
        dict(kind="vblank",seq=10,value=0,cycle=400,frame=23),
    ]

def dump(data):
    return "".join(json.dumps(e,separators=(",",":"))+"\n" for e in data).encode("ascii")

class V84Samples(unittest.TestCase):
    def test_real_value_change_vs_unchanged_is_distinct(self):
        summary=summarize(dump(synthetic_events()))
        self.assertEqual(summary["handler_comparisons"],2)
        self.assertEqual(summary["changed_handlers"],1)
        self.assertEqual(summary["unchanged_handlers"],1)
        self.assertEqual(summary["changed_sample_points"],3)
        self.assertEqual(summary["sample_points_per_handler"],24)
        self.assertFalse(summary["actual_PutPixel_calls_observed"])
        self.assertFalse(summary["same_color_write_distinguished"])
        self.assertTrue(summary["no_actual_pixel_write_inferred_from_zero_delta"])
        self.assertEqual(summary["between_vblank_intervals"][0]["handlers_with_sample_delta"],2)
    def test_refuse_orphan_delta(self):
        data=synthetic_events()
        data[3]["kind"]="gpu_dma2_start"
        with self.assertRaises(Refused):summarize(dump(data))
    def test_refuse_missing_paired_delta(self):
        data=synthetic_events()
        del data[5]
        for e in data[5:]:e["seq"]-=1
        with self.assertRaises(Refused):summarize(dump(data))
    def test_refuse_unrealistic_change_count(self):
        data=synthetic_events()
        data[3]["value"]=25
        with self.assertRaises(Refused):summarize(dump(data))
    def test_refuse_forged_delta_cycle(self):
        data=synthetic_events()
        data[3]["cycle"]=101
        with self.assertRaises(Refused):summarize(dump(data))
    def test_refuse_forged_delta_frame(self):
        data=synthetic_events()
        data[3]["frame"]=21
        with self.assertRaises(Refused):summarize(dump(data))
    def test_refuse_without_changed_values(self):
        data=synthetic_events()
        data[3]["value"]=0
        with self.assertRaises(Refused):summarize(dump(data))
    def test_refuse_without_unchanged_values(self):
        data=synthetic_events()
        data[5]["value"]=1
        with self.assertRaises(Refused):summarize(dump(data))
    def test_v84_gated_by_signed_fixture_and_native_oracle(self):
        text=(ROOT/"tools/apply_map02_v84_pcsx_rearmed.py").read_text()
        self.assertIn("if(vh84_sample_smoke)vh84_set_sampling(1);",text)
        self.assertIn("apply_v83(root)",text)
        self.assertIn("gpu_unai.vram[(160+yi)*1024+40+16*xi]",text)
        self.assertIn("observed_samples!=observed_unai",text)
        self.assertIn("original_retail_MAP02_verified=False",text)
        self.assertIn("HD_replacement_approved=False",text)
    def test_readback_event_is_not_a_write_event(self):
        observer=(ROOT/"tools/map02_v81_event_jsonl.c").read_text()
        self.assertIn('kind="unai_sample_delta"',observer)
        self.assertNotIn('kind="vram_write"',observer)

if __name__=="__main__":
    unittest.main()
