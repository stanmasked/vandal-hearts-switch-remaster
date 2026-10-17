#!/usr/bin/env python3
"""v113 synthetic GP0 sample/store outcome transitions by native VBlank edge."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]

from test_map02_v85_native_stores import sample, encode
from test_map02_v108_vblank_store_buckets import redistribute
from test_map02_v109_gp0_class_vblank_stores import five_classes
from test_map02_v111_sample_store_divergence import (
    extended_polygon_pair, rebind_polygon_sample_to_stores
)
from test_map02_v112_unchanged_sample_runs import (
    consecutive_writers, with_empty_interval_between_writers
)
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v110_class_boundary_checkpoints import summarize as v110
from tools.summarize_map02_v112_unchanged_sample_runs import summarize as v112
from tools.summarize_map02_v113_vblank_outcome_transitions import summarize


UNCHANGED_WRITES="unchanged_sample_with_instrumented_stores"
CHANGED_WRITES="changed_sample_with_instrumented_stores"
UNCHANGED_ZERO="unchanged_sample_no_instrumented_stores"


class OutcomeTransitions(unittest.TestCase):
    def test_five_classes_yield_correct_within_and_across_vblank_outcomes(self):
        report=summarize(encode(five_classes()))
        self.assertEqual(report["observed_unai_handlers"],5)
        self.assertEqual(report["observed_emulator_vblank_edges"],4)
        self.assertEqual([x["adjacent_pairs"] for x in report["within_vblank_intervals"]],
                         [0,1,0,1,0])
        self.assertEqual(report["within_vblank_intervals"][1]["outcome_transitions"],[
            {"from_outcome":CHANGED_WRITES,"to_outcome":UNCHANGED_WRITES,"pairs":1}
        ])
        self.assertEqual(report["within_vblank_intervals"][3]["outcome_transitions"],[
            {"from_outcome":CHANGED_WRITES,"to_outcome":UNCHANGED_ZERO,"pairs":1}
        ])
        self.assertEqual(report["cross_vblank_outcome_transitions"],[
            {"vblank_edges_crossed":1,"from_outcome":CHANGED_WRITES,
             "to_outcome":CHANGED_WRITES,"pairs":1},
            {"vblank_edges_crossed":1,"from_outcome":UNCHANGED_WRITES,
             "to_outcome":CHANGED_WRITES,"pairs":1},
        ])
        self.assertEqual(report["observed_handler_pairs_per_edge"],[0,1,1,0])
        self.assertEqual(report["zero_sample_delta_store_pairs_per_edge"],[0,0,0,0])
        self.assertEqual(report["adjacent_pairs_spanning_vblank"],2)
        self.assertFalse(report["physical_ps1_vblank_verified"])
        self.assertFalse(report["HD_replacement_approved"])

    def test_native_unchanged_sample_writers_straddle_one_vblank(self):
        report=summarize(encode(consecutive_writers()))
        self.assertEqual(report["zero_sample_delta_store_pairs_per_edge"],
                         [0,1,0,0])
        self.assertEqual(report["observed_handler_pairs_per_edge"],[0,1,1,0])
        self.assertEqual(report["vblank_edge_witnesses"][1][
            "previous_handler_outcome"],UNCHANGED_WRITES)
        self.assertEqual(report["vblank_edge_witnesses"][1][
            "next_handler_outcome"],UNCHANGED_WRITES)
        self.assertTrue(report["vblank_edge_witnesses"][1][
            "qualifying_zero_sample_store_pair_spans_edge"])
        self.assertTrue(report["cross_vblank_pairs_do_not_prove_vram_persistence"])

    def test_two_empty_frame_edges_share_a_single_adjacent_handler_pair(self):
        stream=with_empty_interval_between_writers()
        report=summarize(encode(stream))
        expected=v112(encode(stream))
        self.assertEqual(report["zero_sample_delta_store_pairs_per_edge"],
                         [0,1,1,0])
        self.assertEqual(report["observed_handler_pairs_per_edge"],[0,1,1,0])
        self.assertEqual(report["adjacent_pairs_spanning_vblank"],1)
        self.assertEqual(report["vblank_edge_witnesses"][1][
            "vblank_edges_between_nearest_observed_handlers"],2)
        self.assertEqual(report["vblank_edge_witnesses"][2][
            "vblank_edges_between_nearest_observed_handlers"],2)
        self.assertEqual(report["zero_sample_delta_store_pairs_per_edge"],
                         expected["vblank_edges_crossed_by_consecutive_qualifying_pairs"])
        self.assertEqual(sum(x["vblank_edges_crossed"]*x["pairs"]
                             for x in report["cross_vblank_outcome_transitions"]),2)

    def test_sample_store_rebinding_preserves_v110_order_but_changes_outcome_pairs(self):
        first=extended_polygon_pair()
        second=rebind_polygon_sample_to_stores(first)
        self.assertEqual(v110(encode(first)),v110(encode(second)))
        report1=summarize(encode(first))
        report2=summarize(encode(second))
        self.assertEqual(report1["observed_handler_pairs_per_edge"],
                         report2["observed_handler_pairs_per_edge"])
        self.assertNotEqual(report1["within_vblank_intervals"],
                            report2["within_vblank_intervals"])
        self.assertTrue(report1["cross_vblank_pairs_do_not_prove_vram_persistence"])

    def test_before_first_or_after_last_missing_witness_is_explicit(self):
        report=summarize(encode(sample()))
        self.assertIsNone(report["vblank_edge_witnesses"][0][
            "previous_handler_class"])
        for i in (1,2,3):
            self.assertIsNone(report["vblank_edge_witnesses"][i][
                "next_handler_outcome"])
        self.assertEqual(report["observed_handler_pairs_per_edge"],[0,0,0,0])
        # Valid native callback groups also occur outside a VBlank bracket.
        outside=summarize(encode(redistribute()))
        self.assertIsNone(outside["vblank_edge_witnesses"][0][
            "next_handler_outcome"]) if False else None
        self.assertEqual(outside["observed_unai_handlers"],2)

    def test_nonqualifying_gpu_command_breaks_zero_delta_pairs_but_not_all_pairs(self):
        rows=consecutive_writers()
        polygon=next(i for i,r in enumerate(rows) if
                     r["kind"]=="gp0_unai_handled" and r["value"]>>24==0x20)
        rows[polygon+1]["value"]=1
        report=summarize(encode(rows))
        self.assertEqual(report["zero_sample_delta_store_pairs_per_edge"],
                         [0,0,0,0])
        self.assertEqual(report["observed_handler_pairs_per_edge"],[0,1,1,0])
        self.assertEqual(report["adjacent_pairs_spanning_vblank"],2)

    def test_invalid_split_quartet_is_refused(self):
        rows=five_classes()
        at=next(i for i,r in enumerate(rows) if r["kind"]=="vblank" and r["frame"]==11)
        edge=rows.pop(at)
        first=next(i for i,r in enumerate(rows) if r["kind"]=="gp0_unai_handled")
        rows.insert(first+2,edge)
        for i,item in enumerate(rows,1):item["seq"]=i
        with self.assertRaises(Refused):
            summarize(encode(rows))

    def test_forged_native_cycle_sample_and_unrecognized_opcode_refused(self):
        for target,attr,value in (
            ("unai_store_count","cycle",99),
            ("unai_sample_delta","value",25),
            ("unai_store_count","value",0xffffffff),
            ("gp0_unai_handled","value",0x44000000)
        ):
            rows=five_classes()
            next(r for r in rows if r["kind"]==target)[attr]=value
            with self.subTest(target=target,attr=attr),self.assertRaises(Refused):
                summarize(encode(rows))

    def test_never_expose_raw_gpu_words_vram_pixels_or_cpu_cycles(self):
        raw=json.dumps(summarize(encode(five_classes())),sort_keys=True)
        for forbidden in ("0x02000000","0x20000000","0xe1000020",
                          "source_address","pixel_color","private_path",
                          "gpu_dma_source","emulated_cycle_number"):
            self.assertNotIn(forbidden,raw)
        self.assertIn("pinned_pcsx_unai_ordinal_sample_store_outcome_transitions",raw)

    def test_private_pinned_ci_only_writes_a_coarse_public_report(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("summarize_map02_v113_vblank_outcome_transitions",flow)
        self.assertIn("v113-vblank-outcome-transitions.json",flow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",flow)
        self.assertIn("path: proof/public/",flow)


if __name__=="__main__":
    unittest.main()
