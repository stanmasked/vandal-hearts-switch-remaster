#!/usr/bin/env python3
"""Fail closed when private 0..4 native gap bins disagree with v114/v115."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v85_native_stores import sample,encode
from test_map02_v108_vblank_store_buckets import redistribute
from test_map02_v109_gp0_class_vblank_stores import five_classes
from test_map02_v115_identity_runtime import log as oldlog
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v116_gap_identity_runtime import summarize


def gap_line(bins):
    return "VH116_GAPS_PASS "+" ".join(
        f"g{i}={a},{b},{c}" for i,(a,b,c) in enumerate(bins))+"\n"


def base():
    return [(0,0,1),(0,0,0),(0,0,0),(0,0,0),(0,0,0)]


class V116NativeRuntimeBinding(unittest.TestCase):
    def test_only_same_interval_changed_sample_counts(self):
        report=summarize(oldlog()+gap_line(base()),encode(sample()))
        rows=report["native_exact_sample_value_bins_by_intervening_vblank_edges"]
        self.assertEqual(rows[0]["different_delta_counts"],1)
        self.assertEqual(sum(r["different_delta_counts"] for r in rows[1:]),0)
        self.assertTrue(report["bin_totals_checked_against_v114_and_v115"])
        self.assertFalse(report["pixel_values_or_hashes_exported"])
        self.assertFalse(report["HD_replacement_approved"])

    def test_two_observations_bracket_four_vblank_callbacks(self):
        bins=[(0,0,0)]*4+[(0,0,1)]
        log=oldlog(cross_other=1)+gap_line(bins)
        report=summarize(log,encode(redistribute()))
        self.assertEqual(report["native_exact_sample_value_bins_by_intervening_vblank_edges"][4][
            "different_delta_counts"],1)

    def test_same_count_different_exact_values_are_distinguished_per_gap(self):
        records=five_classes()
        first_polygon=next(i for i,r in enumerate(records) if
                           r["kind"]=="gp0_unai_handled" and r["value"]>>24==0x20)
        records[first_polygon+1]["value"]=1
        raw=encode(records)  # 4 pairs: equal-count gap0, 1 other gap0, 2 others gap1
        identical=[(1,0,1),(0,0,2),(0,0,0),(0,0,0),(0,0,0)]
        different=[(0,1,1),(0,0,2),(0,0,0),(0,0,0),(0,0,0)]
        a=summarize(oldlog(handlers=5,identical=1,other=3,cross_other=2)+
                    gap_line(identical),raw)
        b=summarize(oldlog(handlers=5,different=1,other=3,cross_other=2)+
                    gap_line(different),raw)
        self.assertEqual(a["adjacent_observed_handler_pairs"],4)
        self.assertEqual(b["adjacent_observed_handler_pairs"],4)
        self.assertNotEqual(a["native_exact_sample_value_bins_by_intervening_vblank_edges"],
                            b["native_exact_sample_value_bins_by_intervening_vblank_edges"])

    def test_wrong_gap_binding_refused_even_when_global_totals_unchanged(self):
        valid=oldlog(cross_other=1)
        invalid=[(0,0,1)]+[(0,0,0)]*4
        with self.assertRaises(Refused):
            summarize(valid+gap_line(invalid),encode(redistribute()))

    def test_reject_truncated_duplicate_missing_or_out_of_range_native_status(self):
        normal=oldlog()+gap_line(base())
        options=[
            oldlog(),
            normal+gap_line(base()),
            oldlog()+"VH116_GAPS_PASS g0=0,0,1\n",
            oldlog()+gap_line([(0,0,0)]*5),
            oldlog()+gap_line([(0,0,4294967296)]+[(0,0,0)]*4),
        ]
        for i,txt in enumerate(options):
            with self.subTest(i=i),self.assertRaises(Refused):
                summarize(txt,encode(sample()))

    def test_public_output_contains_no_sample_values_or_hidden_fingerprints(self):
        result=json.dumps(summarize(oldlog()+gap_line(base()),encode(sample())))
        for forbidden in ("0xe1000020","private_runtime_log",
                          '"pixel_value":','"pixels":',"vram_address","sha256","snapshot_hash"):
            self.assertNotIn(forbidden,result)
        self.assertIn("host_callback_order_not_emulated_gpu_completion",result)

    def test_pinned_host_executes_new_native_audit(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v116_gap_identity_runtime",flow)
        self.assertIn("v116-sample-gap-summary.json",flow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",flow)


if __name__=="__main__":
    unittest.main()
