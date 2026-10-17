#!/usr/bin/env python3
"""Reconcile native 24-value three-handler return categories to private VBlank gaps."""
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
from test_map02_v116_gap_runtime import gap_line
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v117_triplet_runtime import summarize


def triples(group):
    return "VH117_TRIPLETS_PASS triples="+str(
        sum(sum(t) for t in group))+" "+" ".join(
        f"g{i}={a},{b},{c}" for i,(a,b,c) in enumerate(group))+"\n"


EMPTY=[(0,0,0)]*5


class ThreeHandlerPrivateRuntime(unittest.TestCase):
    def test_two_native_handlers_yield_no_three_handler_window(self):
        stream=oldlog()+gap_line([(0,0,1)]+EMPTY[:4])+triples(EMPTY)
        result=summarize(stream,encode(sample()))
        self.assertEqual(result["native_three_callback_windows"],0)
        self.assertEqual(result["exact_return_to_two_back_total"],0)
        self.assertTrue(result["gap_totals_checked_against_canonical_private_event_order"])
        self.assertFalse(result["raw_pixel_values_and_hashes_exported"])

    def test_five_observed_native_handlers_reconcile_one_two_vblank_gaps(self):
        events=five_classes()
        poly=next(i for i,e in enumerate(events) if
                  e["kind"]=="gp0_unai_handled" and e["value"]>>24==0x20)
        events[poly+1]["value"]=1
        original=encode(events)
        # v116: 2 pairs in bucket gap0 and 2 pairs in gap1.
        native=oldlog(handlers=5,identical=1,other=3,cross_other=2)+gap_line([
            (1,0,1),(0,0,2),(0,0,0),(0,0,0),(0,0,0)])
        # v117: 3 overlapping length-three callback windows;
        # oldest/newest VBlank edge gaps 1,2,1.
        native+=triples([(0,0,0),(0,0,2),(0,1,0),(0,0,0),(0,0,0)])
        report=summarize(native,original)
        self.assertEqual(report["native_three_callback_windows"],3)
        self.assertEqual(report["exact_return_to_two_back_total"],1)
        self.assertEqual(report["bins_by_vblank_edges_oldest_to_newest"][2][
            "returned_to_two_back"],1)
        self.assertFalse(report["physical_PS1_verified"])
        self.assertFalse(report["HD_replacement_approved"])

    def test_relocated_return_to_wrong_gap_refused_even_if_totals_match(self):
        events=five_classes()
        native=oldlog(handlers=5,other=4,cross_other=2)+gap_line([
            (0,0,2),(0,0,2),(0,0,0),(0,0,0),(0,0,0)])
        wrong=triples([(0,0,1),(0,0,1),(0,1,0),(0,0,0),(0,0,0)])
        with self.assertRaises(Refused):
            summarize(native+wrong,encode(events))

    def test_four_vblank_gap_but_no_triplets_when_only_two_handlers(self):
        events=redistribute()
        native=oldlog(cross_other=1)+gap_line([
            (0,0,0),(0,0,0),(0,0,0),(0,0,0),(0,0,1)])
        report=summarize(native+triples(EMPTY),encode(events))
        self.assertEqual(report["observed_unai_handlers"],2)
        self.assertEqual(report["native_three_callback_windows"],0)

    def test_missing_duplicate_partial_or_overflow_status_refused(self):
        valid=oldlog()+gap_line([(0,0,1)]+EMPTY[:4])
        bad=[
            valid,
            valid+triples(EMPTY)*2,
            valid+"VH117_TRIPLETS_PASS triples=0 g0=0,0,0\n",
            valid+triples([(4294967296,0,0)]+EMPTY[:4]),
            valid+triples([(0,1,0)]+EMPTY[:4]),
            valid+triples([(0,0,0)]*4+[(0,0,1)]),
        ]
        for i,item in enumerate(bad):
            with self.subTest(i=i),self.assertRaises(Refused):
                summarize(item,encode(sample()))

    def test_report_never_contains_sample_pixels_or_raw_opcode_words(self):
        result=summarize(
            oldlog()+gap_line([(0,0,1)]+EMPTY[:4])+triples(EMPTY),
            encode(sample()))
        rendered=json.dumps(result,sort_keys=True)
        for token in ('"pixel_value":','"sample_pixels":',
                      "0xe1000020","vram_address","snapshot_hash"):
            self.assertNotIn(token,rendered)
        self.assertTrue(result["only_native_process_compares_actual_24_values"])

    def test_real_pinned_workflow_consumes_native_v117_status(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v117_triplet_runtime",flow)
        self.assertIn("v117-triplet-summary.json",flow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
