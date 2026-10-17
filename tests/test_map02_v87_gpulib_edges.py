#!/usr/bin/env python3
"""v87 guard against corrupted host-only GP0 overlap, mask and X-wrap traces."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v86_gpulib_stores import sample as v86_events,encode
from tools.summarize_map02_v86_gpulib_stores import summarize as prior_audit
from tools.summarize_map02_v87_gpulib_edges import summarize
from tools.verify_map02_v82_native_trace import Refused

KINDS=("gpulib_overlap_store_count","gpulib_overlap_same_count",
       "gpulib_mask_upload_store_count","gpulib_mask_upload_same_count",
       "gpulib_wrap_store_count","gpulib_wrap_same_count")
VALUES=(16,8,12,4,8,4)

def fixture():
    rows=v86_events()
    for kind,value in zip(KINDS,VALUES):
        rows.append(dict(kind=kind,seq=len(rows)+1,value=value,cycle=0,frame=0))
    return rows

class V87EdgeTests(unittest.TestCase):
    def test_valid_provenance_and_counters(self):
        result=summarize(encode(fixture()))
        self.assertTrue(result["all_v87_commands_are_host_submitted"])
        self.assertTrue(result["all_v87_commands_after_emulator_vblank_4"])
        self.assertEqual(result["host_overlap_same_value_stores"],8)
        self.assertEqual(result["host_mask_a0_same_value_stores"],4)
        self.assertEqual(result["host_xwrap_same_value_stores"],4)
        self.assertEqual(result["original_mips_A0_store_count"],32)
        self.assertFalse(result["retail_MAP02_verified"])
        self.assertFalse(result["HD_replacement_approved"])
        self.assertFalse(result["playstation_hardware_mask_equivalence_proven"])
    def test_parent_v86_audit_stays_valid_with_new_tail(self):
        self.assertEqual(prior_audit(encode(fixture()))["host_gp0_80_copy_16bit_store_assignments"],32)
    def test_reject_wrong_overlap_count(self):
        rows=fixture();rows[-6]["value"]=15
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_wrong_mask_count(self):
        rows=fixture();rows[-4]["value"]=8
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_wrong_wrap_same(self):
        rows=fixture();rows[-1]["value"]=5
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_missing_event(self):
        rows=fixture();del rows[-1]
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_duplicate_event(self):
        rows=fixture()
        rows.insert(-1,dict(rows[-1]))
        for i,x in enumerate(rows):x["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_fake_host_emulator_clock(self):
        rows=fixture();rows[-1]["cycle"]=123
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_reject_fake_host_frame(self):
        rows=fixture();rows[-3]["frame"]=20
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_refuse_provenance_override_via_misplaced_v86_block(self):
        rows=fixture()
        rows[-4],rows[-5]=rows[-5],rows[-4]
        for i,x in enumerate(rows):x["seq"]=i+1
        with self.assertRaises(Refused):summarize(encode(rows))
    def test_source_hooks_stay_after_oracle_and_host_owned(self):
        patch=(ROOT/"tools/apply_map02_v87_pcsx_rearmed.py").read_text()
        for expected in ("apply_v86(root)","--vh87-gpulib-edge-smoke",
            "GPU_writeDataMem(overlap_words,4);",
            "GPU_writeDataMem(upload_red,5);",
            "GPU_writeDataMem(wrap_words,4);",
            "VH87_MASK_PRESERVE_REFUSED", "host_after_v86_and_four_interpreted_mips_vblanks",
            "vh80_record(VH87_OVERLAP_STORES,os,0,0);",
            "hardware_gpu_mask_equivalence_verified=False",
            "HD_replacement_approved=False"):
            self.assertIn(expected,patch)

if __name__=="__main__":unittest.main()
